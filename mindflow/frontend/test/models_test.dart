import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/models.dart';

void main() {
  group('enum tolerance', () {
    test('maps an unknown value instead of throwing', () {
      // API.md §12.2: the server may add enum values without a major version.
      // A client that crashes on one turns an additive change into an outage.
      expect(entryTypeFrom('habit'), EntryType.unknown);
      expect(entryStatusFrom('quarantined'), EntryStatus.unknown);
      expect(captureStatusFrom('rehydrating'), CaptureStatus.unknown);
    });

    test('maps null', () {
      expect(entryTypeFrom(null), EntryType.unknown);
    });
  });

  group('CaptureStatus', () {
    test('knows which states are final', () {
      expect(CaptureStatus.completed.isTerminal, isTrue);
      expect(CaptureStatus.transcriptionFailed.isTerminal, isTrue);
      expect(CaptureStatus.partiallyProcessed.isTerminal, isTrue);
      expect(CaptureStatus.transcribing.isTerminal, isFalse);
    });

    test('does not treat an unknown state as final', () {
      // Polling must keep going rather than stop on a state it cannot name.
      expect(CaptureStatus.unknown.isTerminal, isFalse);
    });

    test('pending upload is not "processing"', () {
      expect(CaptureStatus.pendingUpload.isProcessing, isFalse);
      expect(CaptureStatus.extracting.isProcessing, isTrue);
    });
  });

  group('Entry.fromJson', () {
    test('reads the full payload', () {
      final entry = Entry.fromJson({
        'id': 'e1',
        'entry_type': 'task',
        'title': 'Rappeler le DAF',
        'body': null,
        'status': 'needs_review',
        'occurred_at': '2026-06-10T08:00:00Z',
        'version': 3,
        'confidence': 0.62,
        'source': {'capture_id': 'c1'},
        'tags': ['finance'],
        'task': {
          'due_at': '2026-06-12T07:00:00Z',
          'due_precision': 'day',
          'due_raw_expression': 'jeudi',
          'priority': 'high',
        },
      });

      expect(entry.type, EntryType.task);
      expect(entry.needsReview, isTrue);
      expect(entry.version, 3);
      expect(entry.captureId, 'c1');
      expect(entry.tags, ['finance']);
      expect(entry.task?.dueRawExpression, 'jeudi');
      expect(entry.task?.isDone, isFalse);
    });

    test('survives the trimmed summary the capture endpoint returns', () {
      // /v1/captures/{id} embeds entries with four fields only. The list screen
      // and the capture screen share one model, so it has to cope.
      final entry = Entry.fromJson({
        'id': 'e2',
        'entry_type': 'idea',
        'title': 'Tester le partage par lien',
        'status': 'active',
      });
      expect(entry.type, EntryType.idea);
      expect(entry.version, 1);
      expect(entry.task, isNull);
      expect(entry.tags, isEmpty);
    });
  });

  group('Capture.fromJson', () {
    test('flags the degraded mode', () {
      final capture = Capture.fromJson({
        'id': 'c1',
        'status': 'partially_processed',
        'duration_ms': 12000,
        'captured_at': '2026-06-10T08:00:00Z',
        'processing_mode': 'degraded',
        'audio': {'available': true, 'url': 'https://storage.example/c1.m4a'},
        'transcript': {
          'id': 't1',
          'text': 'Rappeler le DAF jeudi',
          'language': 'fr'
        },
        'entries': [],
      });

      expect(capture.isDegraded, isTrue);
      expect(capture.audioUrl, 'https://storage.example/c1.m4a');
      expect(capture.transcript?.text, 'Rappeler le DAF jeudi');
    });

    test('handles a capture whose audio was deleted', () {
      final capture = Capture.fromJson({
        'id': 'c2',
        'status': 'completed',
        'duration_ms': 4000,
        'captured_at': '2026-06-10T08:00:00Z',
        'audio': {'available': false, 'url': null},
      });
      expect(capture.audioUrl, isNull);
      expect(capture.isDegraded, isFalse);
    });
  });

  group('DeclaredCapture.fromJson', () {
    test('reads the signed upload instructions', () {
      final declared = DeclaredCapture.fromJson({
        'id': 'c1',
        'upload': {
          'url': 'https://storage.example/put',
          'headers': {'content-type': 'audio/mp4'},
        },
      });
      expect(declared.uploadUrl, 'https://storage.example/put');
      expect(declared.uploadHeaders['content-type'], 'audio/mp4');
    });

    test('accepts a replay that carries no upload URL', () {
      // Idempotent redeclaration of an already-uploaded capture (ADR-009).
      final declared = DeclaredCapture.fromJson({'id': 'c1', 'upload': null});
      expect(declared.uploadUrl, isNull);
      expect(declared.uploadHeaders, isEmpty);
    });
  });
}
