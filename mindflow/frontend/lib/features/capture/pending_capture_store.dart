/// On-device queue of captures that have been recorded but not yet accepted by
/// the server.
///
/// This is the client half of ADR-009. A capture is durable on the device the
/// moment recording stops; the network exchange that follows is a retry loop,
/// not a precondition. Losing a thought because the metro went into a tunnel is
/// the single failure this product cannot have.
///
/// Persisted as a plain JSON file rather than a local database: the queue holds
/// a handful of rows, is written once per capture, and adding sqlite for that
/// would be a dependency to maintain forever for no measurable gain.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

/// How far a capture got. Each stage is idempotent server-side, so replaying
/// from an earlier stage than strictly necessary is safe — and simpler than
/// trying to be clever about exactly where the failure happened.
enum PendingStage { declared, uploaded }

class PendingCapture {
  const PendingCapture({
    required this.clientCaptureId,
    required this.filePath,
    required this.durationMs,
    required this.capturedAt,
    required this.timezone,
    this.serverCaptureId,
    this.stage = PendingStage.declared,
    this.attempts = 0,
  });

  final String clientCaptureId;
  final String filePath;
  final int durationMs;
  final DateTime capturedAt;
  final String timezone;
  final String? serverCaptureId;
  final PendingStage stage;
  final int attempts;

  PendingCapture copyWith({
    String? serverCaptureId,
    PendingStage? stage,
    int? attempts,
  }) =>
      PendingCapture(
        clientCaptureId: clientCaptureId,
        filePath: filePath,
        durationMs: durationMs,
        capturedAt: capturedAt,
        timezone: timezone,
        serverCaptureId: serverCaptureId ?? this.serverCaptureId,
        stage: stage ?? this.stage,
        attempts: attempts ?? this.attempts,
      );

  Map<String, dynamic> toJson() => {
        'client_capture_id': clientCaptureId,
        'file_path': filePath,
        'duration_ms': durationMs,
        'captured_at': capturedAt.toUtc().toIso8601String(),
        'timezone': timezone,
        'server_capture_id': serverCaptureId,
        'stage': stage.name,
        'attempts': attempts,
      };

  static PendingCapture? fromJson(Map<String, dynamic> json) {
    final id = json['client_capture_id'] as String?;
    final path = json['file_path'] as String?;
    final capturedAt =
        DateTime.tryParse((json['captured_at'] as String?) ?? '');
    if (id == null || path == null || capturedAt == null) return null;
    return PendingCapture(
      clientCaptureId: id,
      filePath: path,
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

class PendingCaptureStore {
  PendingCaptureStore({Directory? directory}) : _directory = directory;

  final Directory? _directory;
  File? _file;

  Future<File> _open() async {
    final existing = _file;
    if (existing != null) return existing;
    final directory = _directory ?? await getApplicationDocumentsDirectory();
    final file = File('${directory.path}/pending_captures.json');
    _file = file;
    return file;
  }

  Future<List<PendingCapture>> load() async {
    final file = await _open();
    if (!file.existsSync()) return const [];
    try {
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is! List) return const [];
      return decoded
          .whereType<Map<String, dynamic>>()
          .map(PendingCapture.fromJson)
          .whereType<PendingCapture>()
          .toList();
    } on FormatException {
      // A truncated write (app killed mid-save) must not brick the queue for
      // good. Drop the file and carry on: the audio files themselves are still
      // on disk and the worst case is a capture the user re-sends by hand.
      await file.delete();
      return const [];
    }
  }

  Future<void> _save(List<PendingCapture> captures) async {
    final file = await _open();
    await file.writeAsString(
      jsonEncode(captures.map((capture) => capture.toJson()).toList()),
      flush: true,
    );
  }

  Future<void> put(PendingCapture capture) async {
    final captures = [...await load()]
      ..removeWhere((item) => item.clientCaptureId == capture.clientCaptureId)
      ..add(capture);
    await _save(captures);
  }

  Future<void> remove(String clientCaptureId, {bool deleteFile = true}) async {
    final captures = await load();
    String? matchedPath;
    for (final item in captures) {
      if (item.clientCaptureId == clientCaptureId) matchedPath = item.filePath;
    }
    await _save(
      captures
          .where((item) => item.clientCaptureId != clientCaptureId)
          .toList(),
    );
    if (deleteFile && matchedPath != null) {
      final file = File(matchedPath);
      if (file.existsSync()) {
        try {
          await file.delete();
        } on FileSystemException {
          // Best effort: an orphan audio file costs disk, not correctness.
        }
      }
    }
  }
}

final pendingCaptureStoreProvider = Provider<PendingCaptureStore>((ref) {
  return PendingCaptureStore();
});
