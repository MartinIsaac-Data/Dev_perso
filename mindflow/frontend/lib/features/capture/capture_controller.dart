/// Drives one capture from microphone to structured entries.
///
/// The client mirrors the server's own staging (Architecture.md §5.1):
///
///     record → declare → PUT audio → complete → poll until terminal
///
/// Each server call is idempotent on `client_capture_id`, so every failure is
/// answered by *retrying the same call*, never by starting over. The audio file
/// stays on disk until the server acknowledges the capture, which is what lets
/// the app be killed at any point in this sequence without losing the thought.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/client.dart';
import '../../core/api/errors.dart';
import '../../core/api/models.dart';
import '../../core/audio/recorder.dart';
import '../../core/time/device_timezone.dart';
import 'pending_capture_store.dart';

enum CapturePhase {
  idle,
  recording,

  /// Uploading, or waiting for a network that will come back. The UI says
  /// "en attente de réseau" rather than showing an error: nothing is lost.
  sending,

  /// Accepted by the server; transcription and extraction are running.
  processing,
  done,
  failed,
}

class CaptureState {
  const CaptureState({
    this.phase = CapturePhase.idle,
    this.elapsed = Duration.zero,
    this.level = -60,
    this.captureId,
    this.capture,
    this.message,
    this.quotaWarning,
    this.pendingCount = 0,
  });

  final CapturePhase phase;
  final Duration elapsed;

  /// Input level in dBFS, for the waveform.
  final double level;
  final String? captureId;
  final Capture? capture;
  final String? message;

  /// Set when the monthly quota is spent. Not an error: the capture is kept and
  /// transcribed, only the AI enrichment is deferred (ADR-026).
  final String? quotaWarning;
  final int pendingCount;

  bool get isRecording => phase == CapturePhase.recording;
  bool get isBusy =>
      phase == CapturePhase.sending || phase == CapturePhase.processing;

  CaptureState copyWith({
    CapturePhase? phase,
    Duration? elapsed,
    double? level,
    String? captureId,
    Capture? capture,
    String? message,
    String? quotaWarning,
    int? pendingCount,
    bool clearMessage = false,
  }) =>
      CaptureState(
        phase: phase ?? this.phase,
        elapsed: elapsed ?? this.elapsed,
        level: level ?? this.level,
        captureId: captureId ?? this.captureId,
        capture: capture ?? this.capture,
        message: clearMessage ? null : (message ?? this.message),
        quotaWarning: quotaWarning ?? this.quotaWarning,
        pendingCount: pendingCount ?? this.pendingCount,
      );
}

class CaptureController extends StateNotifier<CaptureState> {
  CaptureController({
    required MindflowApi api,
    required VoiceRecorder recorder,
    required PendingCaptureStore store,
    required DeviceTimezone timezone,
  })  : _api = api,
        _recorder = recorder,
        _store = store,
        _timezone = timezone,
        super(const CaptureState());

  final MindflowApi _api;
  final VoiceRecorder _recorder;
  final PendingCaptureStore _store;
  final DeviceTimezone _timezone;

  Timer? _ticker;
  StreamSubscription<double>? _levels;
  bool _disposed = false;

  /// `StateNotifier.state` is protected; screens that need this one fact — is
  /// the microphone still open? — ask for it rather than reach into the state.
  bool get isRecordingNow => state.isRecording;

  /// Poll schedule for the processing phase. Front-loaded because a ten-second
  /// capture is usually done in three: a flat 5 s interval would make the fast
  /// case feel as slow as the slow one. Total budget ≈ 100 s, past which the
  /// pipeline is genuinely late and the user is better served by the list view.
  static const _pollDelays = <Duration>[
    Duration(seconds: 1),
    Duration(seconds: 2),
    Duration(seconds: 2),
    Duration(seconds: 3),
    Duration(seconds: 3),
    Duration(seconds: 5),
    Duration(seconds: 5),
    Duration(seconds: 8),
    Duration(seconds: 8),
    Duration(seconds: 10),
    Duration(seconds: 10),
    Duration(seconds: 15),
    Duration(seconds: 15),
  ];

  @override
  void dispose() {
    _disposed = true;
    _ticker?.cancel();
    unawaited(_levels?.cancel());
    super.dispose();
  }

  void _set(CaptureState next) {
    if (!_disposed) state = next;
  }

  // -- recording ----------------------------------------------------------

  Future<void> startRecording() async {
    if (state.isRecording) return;
    try {
      await _recorder.start();
    } on MicrophonePermissionDenied {
      _set(
        state.copyWith(
          phase: CapturePhase.failed,
          message: 'Accès au micro refusé. '
              'Autorisez-le dans les réglages pour capturer.',
        ),
      );
      return;
    }

    _set(const CaptureState(phase: CapturePhase.recording));
    _ticker = Timer.periodic(const Duration(milliseconds: 200), (_) {
      final elapsed = state.elapsed + const Duration(milliseconds: 200);
      if (elapsed >= kMaxRecordingDuration) {
        // Stop on our side rather than let the server reject the upload: the
        // user gets the first ten minutes instead of an error.
        unawaited(stopAndSend());
        return;
      }
      _set(state.copyWith(elapsed: elapsed));
    });
    _levels = _recorder.amplitudes().listen((level) {
      _set(state.copyWith(level: level));
    });
  }

  Future<void> cancelRecording() async {
    _ticker?.cancel();
    await _levels?.cancel();
    _levels = null;
    await _recorder.cancel();
    _set(const CaptureState());
  }

  Future<void> stopAndSend() async {
    if (!state.isRecording) return;
    _ticker?.cancel();
    await _levels?.cancel();
    _levels = null;

    final recording = await _recorder.stop();
    if (recording == null) {
      _set(
        state.copyWith(
          phase: CapturePhase.failed,
          message: "L'enregistrement n'a pas pu être finalisé.",
        ),
      );
      return;
    }
    if (recording.isTooShort) {
      try {
        await recording.file.delete();
      } on FileSystemException {
        // Nothing to do; an empty file is harmless.
      }
      _set(const CaptureState(message: 'Enregistrement trop court.'));
      return;
    }

    final pending = PendingCapture(
      clientCaptureId: recording.clientCaptureId,
      filePath: recording.file.path,
      durationMs: recording.duration.inMilliseconds,
      capturedAt: recording.startedAt,
      timezone: await _timezone.refresh(),
    );
    // Persisted *before* the first network call: from here the capture exists
    // whatever happens to the process.
    await _store.put(pending);

    _set(state.copyWith(
        phase: CapturePhase.sending, elapsed: recording.duration));
    await _send(pending);
  }

  // -- sending ------------------------------------------------------------

  Future<void> _send(PendingCapture pending) async {
    try {
      var current = pending;

      if (current.stage == PendingStage.declared) {
        final declared = await _api.declareCapture(
          clientCaptureId: current.clientCaptureId,
          durationMs: current.durationMs,
          capturedAt: current.capturedAt,
          timezone: current.timezone,
          audioBytes: await _sizeOf(current.filePath),
        );
        current = current.copyWith(serverCaptureId: declared.id);
        await _store.put(current);
        _set(state.copyWith(
            captureId: declared.id, quotaWarning: declared.quotaWarning));

        // No upload URL on a replay whose audio the server already holds.
        if (declared.uploadUrl != null) {
          final bytes = await File(current.filePath).readAsBytes();
          await _api.uploadAudio(
            url: declared.uploadUrl!,
            bytes: bytes,
            headers: declared.uploadHeaders,
          );
        }
        current = current.copyWith(stage: PendingStage.uploaded);
        await _store.put(current);
      }

      final captureId = current.serverCaptureId;
      if (captureId == null) {
        throw StateError('capture déclarée sans identifiant serveur');
      }

      await _api.completeCapture(captureId);
      // The server owns the capture now; the local copy is redundant.
      await _store.remove(current.clientCaptureId);

      _set(
          state.copyWith(phase: CapturePhase.processing, captureId: captureId));
      await _pollUntilTerminal(captureId);
    } on ApiException catch (error) {
      await _handleSendFailure(pending, error.userMessage,
          retriable: !error.isAuth);
    } on SocketException {
      await _handleSendFailure(
        pending,
        'Pas de réseau. La capture est conservée et sera envoyée automatiquement.',
        retriable: true,
      );
    } catch (_) {
      await _handleSendFailure(
        pending,
        "L'envoi a échoué. La capture est conservée sur l'appareil.",
        retriable: true,
      );
    }
  }

  Future<void> _handleSendFailure(
    PendingCapture pending,
    String message, {
    required bool retriable,
  }) async {
    if (retriable) {
      await _store.put(pending.copyWith(attempts: pending.attempts + 1));
    }
    _set(state.copyWith(phase: CapturePhase.failed, message: message));
    await refreshPendingCount();
  }

  Future<int?> _sizeOf(String path) async {
    final file = File(path);
    return file.existsSync() ? file.lengthSync() : null;
  }

  Future<void> _pollUntilTerminal(String captureId) async {
    for (final delay in _pollDelays) {
      await Future<void>.delayed(delay);
      if (_disposed) return;
      try {
        final capture = await _api.getCapture(captureId);
        _set(state.copyWith(capture: capture));
        if (capture.status.isTerminal) {
          _set(
            state.copyWith(
              phase: CapturePhase.done,
              capture: capture,
              message: _terminalMessage(capture),
            ),
          );
          return;
        }
      } on ApiException {
        // A failed poll says nothing about the capture, which is safe in the
        // database. Keep polling; the next attempt usually succeeds.
        continue;
      }
    }
    // Still running: not a failure. The capture appears in the list as soon as
    // the worker finishes.
    _set(
      state.copyWith(
        phase: CapturePhase.done,
        message: 'Traitement en cours. Le résultat apparaîtra dans vos notes.',
      ),
    );
  }

  String? _terminalMessage(Capture capture) => switch (capture.status) {
        CaptureStatus.transcriptionFailed =>
          "La transcription a échoué. L'audio est conservé et sera retenté.",
        CaptureStatus.partiallyProcessed =>
          "La transcription est disponible ; l'analyse sera reprise plus tard.",
        _ => null,
      };

  // -- offline queue ------------------------------------------------------

  Future<void> refreshPendingCount() async {
    final pending = await _store.load();
    _set(state.copyWith(pendingCount: pending.length));
  }

  /// Replays everything still queued. Called at app start and after a manual
  /// retry. Sequential on purpose: a phone that just regained connectivity on a
  /// weak link does worse with five parallel uploads than with one.
  Future<void> flushPending() async {
    final pending = await _store.load();
    for (final capture in pending) {
      if (!File(capture.filePath).existsSync()) {
        // The OS reclaimed the file; nothing left to send.
        await _store.remove(capture.clientCaptureId, deleteFile: false);
        continue;
      }
      _set(state.copyWith(phase: CapturePhase.sending, clearMessage: true));
      await _send(capture);
      if (state.phase == CapturePhase.failed) break;
    }
    await refreshPendingCount();
  }

  void reset() => _set(CaptureState(pendingCount: state.pendingCount));
}

final captureControllerProvider =
    StateNotifierProvider<CaptureController, CaptureState>((ref) {
  return CaptureController(
    api: ref.watch(apiProvider),
    recorder: ref.watch(voiceRecorderProvider),
    store: ref.watch(pendingCaptureStoreProvider),
    timezone: ref.watch(deviceTimezoneProvider),
  );
});
