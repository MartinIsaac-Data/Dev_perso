/// On-device queue of captures that have been recorded but not yet accepted by
/// the server.
///
/// This is the client half of ADR-009. A capture is durable on the device the
/// moment recording stops; the network exchange that follows is a retry loop,
/// not a precondition. Losing a thought because the metro went into a tunnel is
/// the single failure this product cannot have.
///
/// Persisted as one JSON document rather than a local database: the queue holds
/// a handful of rows, is written once per capture, and adding sqlite for that
/// would be a dependency to maintain forever for no measurable gain.
///
/// The document goes through `DocumentStore`, so the same queue is a file on a
/// phone and a `localStorage` entry in a browser (ADR-061). The audio it points
/// at goes through `BlobStore` — different sizes, different stakes, different
/// mechanisms.
library;

import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/audio/recorder.dart' show blobStoreProvider;
import '../../core/storage/blob_store.dart';
import '../../core/storage/document_store.dart';

/// How far a capture got. Each stage is idempotent server-side, so replaying
/// from an earlier stage than strictly necessary is safe — and simpler than
/// trying to be clever about exactly where the failure happened.
enum PendingStage { declared, uploaded }

class PendingCapture {
  const PendingCapture({
    required this.clientCaptureId,
    required this.durationMs,
    required this.capturedAt,
    required this.timezone,
    this.audioFormat = 'm4a',
    this.serverCaptureId,
    this.stage = PendingStage.declared,
    this.attempts = 0,
  });

  final String clientCaptureId;

  /// The format the audio was recorded in, carried because this entry may be
  /// declared to the server weeks after the browser or device that produced it
  /// decided on it.
  final String audioFormat;
  final int durationMs;
  final DateTime capturedAt;
  final String timezone;
  final String? serverCaptureId;
  final PendingStage stage;
  final int attempts;

  PendingCapture copyWith({
    String? audioFormat,
    String? serverCaptureId,
    PendingStage? stage,
    int? attempts,
  }) =>
      PendingCapture(
        clientCaptureId: clientCaptureId,
        audioFormat: audioFormat ?? this.audioFormat,
        durationMs: durationMs,
        capturedAt: capturedAt,
        timezone: timezone,
        serverCaptureId: serverCaptureId ?? this.serverCaptureId,
        stage: stage ?? this.stage,
        attempts: attempts ?? this.attempts,
      );

  Map<String, dynamic> toJson() => {
        'client_capture_id': clientCaptureId,
        'audio_format': audioFormat,
        'duration_ms': durationMs,
        'captured_at': capturedAt.toUtc().toIso8601String(),
        'timezone': timezone,
        'server_capture_id': serverCaptureId,
        'stage': stage.name,
        'attempts': attempts,
      };

  static PendingCapture? fromJson(Map<String, dynamic> json) {
    final id = json['client_capture_id'] as String?;
    final capturedAt =
        DateTime.tryParse((json['captured_at'] as String?) ?? '');
    if (id == null || capturedAt == null) return null;
    return PendingCapture(
      clientCaptureId: id,
      audioFormat: (json['audio_format'] as String?) ?? 'm4a',
      durationMs: (json['duration_ms'] as num?)?.toInt() ?? 0,
      capturedAt: capturedAt,
      timezone: (json['timezone'] as String?) ?? 'Europe/Paris',
      serverCaptureId: json['server_capture_id'] as String?,
      stage: PendingStage.values.firstWhere(
        (stage) => stage.name == json['stage'],
        orElse: () => PendingStage.declared,
      ),
      attempts: (json['attempts'] as num?)?.toInt() ?? 0,
    );
  }
}

const _documentName = 'pending_captures.json';

class PendingCaptureStore {
  PendingCaptureStore({DocumentStore? documents, BlobStore? blobs})
      : _documents = documents ?? createDocumentStore(),
        _blobs = blobs ?? createBlobStore();

  final DocumentStore _documents;
  final BlobStore _blobs;

  Future<List<PendingCapture>> load() async {
    final raw = await _documents.read(_documentName);
    if (raw == null || raw.isEmpty) return const [];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return const [];
      return decoded
          .whereType<Map<String, dynamic>>()
          .map(PendingCapture.fromJson)
          .whereType<PendingCapture>()
          .toList();
    } on FormatException {
      // A truncated write (app killed mid-save) must not brick the queue for
      // good. Drop the document and carry on: the audio itself is still stored
      // and the worst case is a capture the user re-sends by hand.
      await _documents.delete(_documentName);
      return const [];
    }
  }

  Future<void> _save(List<PendingCapture> captures) => _documents.write(
        _documentName,
        jsonEncode(captures.map((capture) => capture.toJson()).toList()),
      );

  Future<void> put(PendingCapture capture) async {
    final captures = [...await load()]
      ..removeWhere((item) => item.clientCaptureId == capture.clientCaptureId)
      ..add(capture);
    await _save(captures);
  }

  Future<void> remove(String clientCaptureId, {bool deleteAudio = true}) async {
    final captures = await load();
    await _save(
      captures
          .where((item) => item.clientCaptureId != clientCaptureId)
          .toList(),
    );
    if (deleteAudio) await _blobs.delete(clientCaptureId);
  }
}

final pendingCaptureStoreProvider = Provider<PendingCaptureStore>((ref) {
  return PendingCaptureStore(blobs: ref.watch(blobStoreProvider));
});
