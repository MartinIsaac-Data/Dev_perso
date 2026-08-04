/// What this platform can actually record.
///
/// Phase 1 hard-coded AAC-LC in an MPEG-4 container, which is right on every
/// native target and wrong in most browsers: `MediaRecorder` in Chrome and
/// Firefox produces Opus in a WebM container and refuses AAC outright. A build
/// that asks for AAC on the web fails at `start()`, which the user reads as a
/// microphone that does not work.
///
/// The server already accepts both (`AudioFormat.WEBM`, `AudioFormat.OPUS`,
/// `AudioFormat.M4A`), so this is purely a client-side choice — and it belongs
/// in one place rather than in the recorder, because the queue has to declare
/// the same format weeks later when it finally gets a network.
library;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:record/record.dart';

class AudioProfile {
  const AudioProfile({
    required this.encoder,
    required this.format,
    required this.mimeType,
  });

  final AudioEncoder encoder;

  /// The `audio_format` the API is told about, and the file extension used on
  /// native. One value for both so they cannot drift.
  final String format;
  final String mimeType;

  /// 16 kHz mono. Whisper resamples to 16 kHz anyway, so recording higher only
  /// inflates the upload; mono because a voice memo has one speaker.
  static const sampleRate = 16000;
  static const numChannels = 1;
  static const bitRate = 32000;

  RecordConfig get config => RecordConfig(
        encoder: encoder,
        sampleRate: sampleRate,
        numChannels: numChannels,
        bitRate: bitRate,
      );

  /// The profile for the platform this build targets.
  ///
  /// Opus in WebM is the one combination every current browser engine can
  /// produce. Safari gained it in 17; older Safari will fail at `start()` and
  /// the capture screen reports a microphone that could not be opened, which is
  /// accurate.
  static AudioProfile forPlatform() => kIsWeb ? webm : m4a;

  static const m4a = AudioProfile(
    encoder: AudioEncoder.aacLc,
    format: 'm4a',
    mimeType: 'audio/mp4',
  );

  static const webm = AudioProfile(
    encoder: AudioEncoder.opus,
    format: 'webm',
    mimeType: 'audio/webm',
  );

  static AudioProfile byFormat(String format) => switch (format) {
        'webm' => webm,
        _ => m4a,
      };
}
