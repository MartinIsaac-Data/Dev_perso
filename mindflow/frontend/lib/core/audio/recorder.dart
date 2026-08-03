/// Microphone capture.
///
/// Two decisions worth stating, because both are load-bearing:
///
/// 1. **The recorder writes to a file, not to memory.** A three-minute capture
///    held in RAM is lost when the OS kills a backgrounded app — precisely the
///    moment a voice-first product cannot afford to lose data. On disk, the
///    partial file survives and the capture can still be sent.
///
/// 2. **The `client_capture_id` is generated before recording starts**, and the
///    file is named after it. That is what makes the whole offline-retry story
///    work (ADR-009): the identity of a capture exists before its bytes do, so a
///    retry after a crash refers to the same capture instead of creating a
///    second one.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:uuid/uuid.dart';

/// 16 kHz mono AAC. Whisper resamples to 16 kHz anyway, so recording higher
/// only inflates the upload; mono because a voice memo has one speaker and
/// stereo doubles the bytes for nothing.
const kRecordConfig = RecordConfig(
  encoder: AudioEncoder.aacLc,
  sampleRate: 16000,
  numChannels: 1,
  bitRate: 32000,
);

const kAudioFormat = 'm4a';

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
    required this.file,
    required this.duration,
    required this.startedAt,
  });

  /// Generated before the first byte was recorded — the idempotency key.
  final String clientCaptureId;
  final File file;
  final Duration duration;
  final DateTime startedAt;

  bool get isTooShort => duration < kMinRecordingDuration;
}

class VoiceRecorder {
  VoiceRecorder({AudioRecorder? recorder, Uuid? uuid})
      : _recorder = recorder ?? AudioRecorder(),
        _uuid = uuid ?? const Uuid();

  final AudioRecorder _recorder;
  final Uuid _uuid;

  String? _clientCaptureId;
  String? _path;
  DateTime? _startedAt;

  bool get isRecording => _startedAt != null;

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
    final directory = await getApplicationDocumentsDirectory();
    final captures = Directory('${directory.path}/captures');
    if (!captures.existsSync()) {
      captures.createSync(recursive: true);
    }
    final path = '${captures.path}/$id.$kAudioFormat';

    await _recorder.start(kRecordConfig, path: path);
    _clientCaptureId = id;
    _path = path;
    _startedAt = DateTime.now();
    return id;
  }

  /// Stops and returns the file. Null when nothing was being recorded, or when
  /// the platform handed back no file — a real case on a denied permission that
  /// slipped past the check.
  Future<RecordingResult?> stop() async {
    final id = _clientCaptureId;
    final startedAt = _startedAt;
    if (id == null || startedAt == null) return null;

    final resultPath = await _recorder.stop() ?? _path;
    final duration = DateTime.now().difference(startedAt);
    _clientCaptureId = null;
    _startedAt = null;
    _path = null;

    if (resultPath == null) return null;
    final file = File(resultPath);
    if (!file.existsSync()) return null;

    return RecordingResult(
      clientCaptureId: id,
      file: file,
      duration: duration,
      startedAt: startedAt,
    );
  }

  /// Aborts and deletes. Used when the user cancels: an abandoned recording must
  /// not linger on the device.
  Future<void> cancel() async {
    if (_startedAt == null) return;
    final path = await _recorder.stop() ?? _path;
    _clientCaptureId = null;
    _startedAt = null;
    _path = null;
    if (path != null) {
      final file = File(path);
      if (file.existsSync()) {
        try {
          await file.delete();
        } on FileSystemException {
          // A leftover temp file is not worth failing a cancel over.
        }
      }
    }
  }

  Future<void> dispose() => _recorder.dispose();
}

final voiceRecorderProvider = Provider<VoiceRecorder>((ref) {
  final recorder = VoiceRecorder();
  ref.onDispose(recorder.dispose);
  return recorder;
});
