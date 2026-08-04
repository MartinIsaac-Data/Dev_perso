/// Microphone capture.
///
/// Three decisions worth stating, because all three are load-bearing:
///
/// 1. **The recorder writes to storage, not to memory.** A three-minute capture
///    held in RAM is lost when the OS kills a backgrounded app — precisely the
///    moment a voice-first product cannot afford to lose data.
///
/// 2. **The `client_capture_id` is generated before recording starts**, and the
///    bytes are stored under it. That is what makes the whole offline-retry
///    story work (ADR-009): the identity of a capture exists before its bytes
///    do, so a retry after a crash refers to the same capture instead of
///    creating a second one.
///
/// 3. **Where those bytes live is not this class's business** (ADR-061). Phase 1
///    returned a `File`, which is a lie in a browser — `dart:io` compiles for
///    the web and throws at run time. The result now carries the *key*, and the
///    `BlobStore` behind it knows whether that means a file or an IndexedDB
///    row.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';
import 'package:uuid/uuid.dart';

import '../storage/blob_store.dart';
import 'audio_profile.dart';

/// Below the ceiling enforced by the API, so the user is told before uploading
/// rather than after (Settings.max_capture_duration_ms).
const kMaxRecordingDuration = Duration(minutes: 10);

/// Anything shorter is a slip of the thumb, not a capture.
const kMinRecordingDuration = Duration(milliseconds: 700);

class MicrophonePermissionDenied implements Exception {
  const MicrophonePermissionDenied();
}

class RecordingResult {
  const RecordingResult({
    required this.clientCaptureId,
    required this.audioFormat,
    required this.duration,
    required this.startedAt,
  });

  /// Generated before the first byte was recorded — the idempotency key, and
  /// the key the audio is stored under.
  final String clientCaptureId;

  /// `m4a` on native, `webm` in a browser. Carried rather than assumed: the
  /// queue may declare this capture weeks later.
  final String audioFormat;
  final Duration duration;
  final DateTime startedAt;

  bool get isTooShort => duration < kMinRecordingDuration;
}

class VoiceRecorder {
  VoiceRecorder({
    AudioRecorder? recorder,
    BlobStore? blobs,
    AudioProfile? profile,
    Uuid? uuid,
  })  : _recorder = recorder ?? AudioRecorder(),
        _blobs = blobs ?? createBlobStore(),
        _profile = profile ?? AudioProfile.forPlatform(),
        _uuid = uuid ?? const Uuid();

  final AudioRecorder _recorder;
  final BlobStore _blobs;
  final AudioProfile _profile;
  final Uuid _uuid;

  String? _clientCaptureId;
  DateTime? _startedAt;

  bool get isRecording => _startedAt != null;

  String get audioFormat => _profile.format;

  /// Live input level, in dBFS, for the waveform. Silent input sits near -60.
  Stream<double> amplitudes(
          {Duration interval = const Duration(milliseconds: 120)}) =>
      _recorder
          .onAmplitudeChanged(interval)
          .map((amplitude) => amplitude.current);

  Future<String> start() async {
    if (!await _recorder.hasPermission()) {
      throw const MicrophonePermissionDenied();
    }

    final id = _uuid.v4();
    // Null in a browser: `MediaRecorder` picks its own destination and hands
    // back a blob URL at the end. `record` wants the argument regardless, and
    // an empty string is how its web implementation reads "your choice".
    final target = await _blobs.recordingTarget(id, _profile.format);

    await _recorder.start(_profile.config, path: target ?? '');
    _clientCaptureId = id;
    _startedAt = DateTime.now();
    return id;
  }

  /// Stops and stores the audio. Null when nothing was being recorded, or when
  /// the platform handed back nothing storable — a real case on a permission
  /// revoked mid-recording.
  Future<RecordingResult?> stop() async {
    final id = _clientCaptureId;
    final startedAt = _startedAt;
    if (id == null || startedAt == null) return null;

    final source = await _recorder.stop();
    final duration = DateTime.now().difference(startedAt);
    _clientCaptureId = null;
    _startedAt = null;

    if (source == null) return null;
    // Awaited before returning: the caller's next act is to write a queue entry
    // pointing at this key, and an entry pointing at bytes that never landed is
    // worse than no entry at all.
    final stored = await _blobs.ingest(id, source, extension: _profile.format);
    if (!stored) return null;

    return RecordingResult(
      clientCaptureId: id,
      audioFormat: _profile.format,
      duration: duration,
      startedAt: startedAt,
    );
  }

  /// Aborts and deletes. Used when the user cancels: an abandoned recording must
  /// not linger on the device.
  Future<void> cancel() async {
    if (_startedAt == null) return;
    final id = _clientCaptureId;
    final source = await _recorder.stop();
    _clientCaptureId = null;
    _startedAt = null;
    if (id == null) return;
    // Ingest, then delete. On native the recorder wrote straight to the target
    // and there is a file to remove; in a browser the object URL has to be
    // revoked, and `ingest` is what does that.
    if (source != null) {
      await _blobs.ingest(id, source, extension: _profile.format);
    }
    await _blobs.delete(id);
  }

  Future<void> dispose() => _recorder.dispose();
}

final blobStoreProvider = Provider<BlobStore>((ref) => createBlobStore());

final voiceRecorderProvider = Provider<VoiceRecorder>((ref) {
  final recorder = VoiceRecorder(blobs: ref.watch(blobStoreProvider));
  ref.onDispose(recorder.dispose);
  return recorder;
});
