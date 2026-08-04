/// Driving one live meeting from the client.
///
/// The controller's whole job is the block loop: record, cut every thirty
/// seconds, send, keep recording. Two decisions in it are worth stating.
///
/// **Blocks overlap.** Each one is cut a little before the previous one ended,
/// because a hard cut lands mid-word roughly as often as not and the two halves
/// are then transcribed as two wrong words. The server removes the repeated
/// seam (`domain.meeting.stitch`), so the cost of the overlap is a little extra
/// transcription and the benefit is that no word is lost at a boundary
/// (ADR-013).
///
/// **A failed block does not stop the meeting.** The room did not pause. A
/// block that fails to send is counted and dropped, and recording continues —
/// the alternative, ending the meeting on a network blip, would be the worst
/// possible response to the situation this feature exists for.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/client.dart';
import '../../core/api/errors.dart';
import '../../core/api/meeting_models.dart';
import '../../core/audio/audio_profile.dart';
import '../../core/audio/recorder.dart';
import '../../core/storage/blob_store.dart';

/// How long each block covers. Thirty seconds is the compromise: shorter blocks
/// reach the panel sooner and cost more per minute of meeting; longer ones make
/// a suggestion arrive after the moment it was useful in the room.
const kBlockDuration = Duration(seconds: 30);

enum MeetingPhase { idle, recording, closing, closed, failed }

class MeetingState {
  const MeetingState({
    this.phase = MeetingPhase.idle,
    this.meeting,
    this.suggestions = const [],
    this.report,
    this.elapsed = Duration.zero,
    this.wordCount = 0,
    this.blocksSent = 0,
    this.blocksLost = 0,
    this.message,
  });

  final MeetingPhase phase;
  final Meeting? meeting;
  final List<MeetingSuggestion> suggestions;
  final MeetingReport? report;
  final Duration elapsed;
  final int wordCount;
  final int blocksSent;

  /// Blocks that never reached the server. Shown rather than hidden: a
  /// transcript with holes produces a summary that is confidently incomplete,
  /// and the person in the room is the only one who can judge whether that
  /// matters.
  final int blocksLost;
  final String? message;

  bool get isRecording => phase == MeetingPhase.recording;
  bool get isBusy => phase == MeetingPhase.closing;

  MeetingState copyWith({
    MeetingPhase? phase,
    Meeting? meeting,
    List<MeetingSuggestion>? suggestions,
    MeetingReport? report,
    Duration? elapsed,
    int? wordCount,
    int? blocksSent,
    int? blocksLost,
    String? message,
    bool clearMessage = false,
  }) =>
      MeetingState(
        phase: phase ?? this.phase,
        meeting: meeting ?? this.meeting,
        suggestions: suggestions ?? this.suggestions,
        report: report ?? this.report,
        elapsed: elapsed ?? this.elapsed,
        wordCount: wordCount ?? this.wordCount,
        blocksSent: blocksSent ?? this.blocksSent,
        blocksLost: blocksLost ?? this.blocksLost,
        message: clearMessage ? null : (message ?? this.message),
      );
}

class MeetingController extends StateNotifier<MeetingState> {
  MeetingController({
    required MindflowApi api,
    required VoiceRecorder recorder,
    required BlobStore blobs,
  })  : _api = api,
        _recorder = recorder,
        _blobs = blobs,
        super(const MeetingState());

  final MindflowApi _api;
  final VoiceRecorder _recorder;
  final BlobStore _blobs;

  Timer? _ticker;
  Timer? _blockTimer;
  bool _disposed = false;
  bool _sending = false;

  @override
  void dispose() {
    _disposed = true;
    _ticker?.cancel();
    _blockTimer?.cancel();
    super.dispose();
  }

  void _set(MeetingState next) {
    if (!_disposed) state = next;
  }

  /// Looks for a meeting left open by a previous run.
  Future<void> restore() async {
    try {
      final meeting = await _api.liveMeeting();
      if (meeting == null) return;
      _set(
        state.copyWith(
          meeting: meeting,
          suggestions: meeting.suggestions,
          wordCount: meeting.wordCount,
          message: 'Une réunion est encore ouverte. Reprenez ou terminez-la.',
        ),
      );
    } on ApiException {
      // Nothing to restore is indistinguishable from being offline here, and
      // neither is worth an error on a screen the user just opened.
    }
  }

  Future<void> start({String? title}) async {
    if (state.isRecording) return;
    try {
      final meeting = state.meeting?.status.isLive == true
          ? state.meeting!
          : await _api.openMeeting(title: title);
      await _recorder.start();
      _set(
        MeetingState(
          phase: MeetingPhase.recording,
          meeting: meeting,
          suggestions: meeting.suggestions,
          wordCount: meeting.wordCount,
        ),
      );
      _startTimers();
    } on MicrophonePermissionDenied {
      _set(
        state.copyWith(
          phase: MeetingPhase.failed,
          message: 'Accès au micro refusé. Autorisez-le pour transcrire.',
        ),
      );
    } on ApiException catch (error) {
      _set(state.copyWith(
          phase: MeetingPhase.failed, message: error.userMessage));
    }
  }

  void _startTimers() {
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      _set(state.copyWith(elapsed: state.elapsed + const Duration(seconds: 1)));
    });
    _blockTimer = Timer.periodic(kBlockDuration, (_) => unawaited(_cutBlock()));
  }

  /// Stop, send what was recorded, and immediately start recording again.
  ///
  /// The gap between the two is the reason blocks overlap on the server side:
  /// whatever is said during it would otherwise be lost, so the next block is
  /// expected to repeat the tail of this one.
  Future<void> _cutBlock({bool restart = true}) async {
    if (_sending || !state.isRecording) return;
    _sending = true;
    try {
      final recording = await _recorder.stop();
      if (restart && !_disposed) {
        // Restarted before the upload so the microphone is closed for as short
        // a time as possible.
        await _recorder.start();
      }
      if (recording == null) return;

      final bytes = await _blobs.read(recording.clientCaptureId);
      await _blobs.delete(recording.clientCaptureId);
      if (bytes == null || bytes.isEmpty) {
        _set(state.copyWith(blocksLost: state.blocksLost + 1));
        return;
      }
      await _send(bytes, recording.audioFormat);
    } finally {
      _sending = false;
    }
  }

  Future<void> _send(Uint8List bytes, String format) async {
    final meeting = state.meeting;
    if (meeting == null) return;
    try {
      final block = await _api.sendMeetingAudio(
        meeting.id,
        bytes,
        mediaType: AudioProfile.byFormat(format).mimeType,
      );
      _set(
        state.copyWith(
          wordCount: block.wordCount,
          blocksSent: state.blocksSent + 1,
          suggestions: _merge(state.suggestions, block.newSuggestions),
          clearMessage: true,
        ),
      );
    } on ApiException {
      // Counted, not raised. The room did not stop talking, and ending the
      // meeting on a network blip is the worst possible response to it.
      _set(state.copyWith(blocksLost: state.blocksLost + 1));
    }
  }

  /// Close the meeting and fetch its report.
  Future<void> close() async {
    final meeting = state.meeting;
    if (meeting == null) return;

    _ticker?.cancel();
    _blockTimer?.cancel();
    // One last block: the final thirty seconds are where people agree what
    // happens next, which is exactly what this feature is for.
    if (state.isRecording) await _cutBlock(restart: false);
    _set(state.copyWith(phase: MeetingPhase.closing, clearMessage: true));

    try {
      final outcome = await _api.closeMeeting(meeting.id);
      _set(
        state.copyWith(
          phase: MeetingPhase.closed,
          meeting: outcome.meeting,
          suggestions: outcome.meeting.suggestions,
          report: outcome.report,
          wordCount: outcome.meeting.wordCount,
        ),
      );
    } on ApiException catch (error) {
      // The meeting is still open server-side, so nothing is lost and the user
      // can try again. Saying so is the difference between a retry and a panic.
      _set(
        state.copyWith(
          phase: MeetingPhase.failed,
          message: '${error.userMessage} '
              'La réunion reste ouverte : réessayez de la terminer.',
        ),
      );
    }
  }

  /// Discard without producing anything.
  Future<void> abandon() async {
    final meeting = state.meeting;
    _ticker?.cancel();
    _blockTimer?.cancel();
    if (state.isRecording) await _recorder.cancel();
    if (meeting != null) {
      try {
        await _api.abandonMeeting(meeting.id);
      } on ApiException {
        // Best effort. A row left `live` is swept server-side.
      }
    }
    _set(const MeetingState());
  }

  void reset() => _set(const MeetingState());

  /// Merge without repeating.
  ///
  /// The server already deduplicates, so today this only guards the resume
  /// path: a meeting reopened with suggestions on it, then a block that reports
  /// one of them again. It exists ahead of its second caller on purpose —
  /// `GET /v1/meetings/{id}/stream` is the other source, and this client does
  /// not consume it yet (`TODO.md` B15). When it does, the same suggestion will
  /// arrive twice by construction.
  static List<MeetingSuggestion> _merge(
    List<MeetingSuggestion> existing,
    List<MeetingSuggestion> arriving,
  ) {
    final seen = {for (final item in existing) item.key};
    return [
      ...existing,
      ...arriving.where((item) => seen.add(item.key)),
    ];
  }
}

final meetingControllerProvider =
    StateNotifierProvider<MeetingController, MeetingState>((ref) {
  return MeetingController(
    api: ref.watch(apiProvider),
    recorder: ref.watch(voiceRecorderProvider),
    blobs: ref.watch(blobStoreProvider),
  );
});

final recentMeetingsProvider = FutureProvider.autoDispose<List<Meeting>>((ref) {
  return ref.watch(apiProvider).listMeetings();
});
