/// The queue, against in-memory stand-ins for both halves of storage.
///
/// It used to run against a temporary directory, which tied the test to
/// `dart:io` and therefore tested only the platforms that have files. The fakes
/// implement the same ports the browser implementations do, so what is asserted
/// here is true on every target rather than on four of six.
library;

import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/features/capture/pending_capture_store.dart';

import 'support/fake_storage.dart';

void main() {
  late FakeDocumentStore documents;
  late FakeBlobStore blobs;
  late PendingCaptureStore store;

  setUp(() {
    documents = FakeDocumentStore();
    blobs = FakeBlobStore();
    store = PendingCaptureStore(documents: documents, blobs: blobs);
  });

  PendingCapture sample(String id) => PendingCapture(
        clientCaptureId: id,
        durationMs: 4200,
        capturedAt: DateTime.utc(2026, 6, 10, 8),
        timezone: 'Europe/Paris',
      );

  test('is empty before anything is queued', () async {
    expect(await store.load(), isEmpty);
  });

  test('round-trips a capture', () async {
    await store.put(sample('a'));
    final loaded = await store.load();

    expect(loaded, hasLength(1));
    expect(loaded.single.clientCaptureId, 'a');
    expect(loaded.single.durationMs, 4200);
    expect(loaded.single.capturedAt, DateTime.utc(2026, 6, 10, 8));
    expect(loaded.single.stage, PendingStage.declared);
  });

  test('replaces rather than duplicates on re-put', () async {
    await store.put(sample('a'));
    await store
        .put(sample('a').copyWith(stage: PendingStage.uploaded, attempts: 2));

    final loaded = await store.load();
    expect(loaded, hasLength(1));
    expect(loaded.single.stage, PendingStage.uploaded);
    expect(loaded.single.attempts, 2);
  });

  test('carries the recorded format so a late replay declares it right',
      () async {
    // A capture recorded in a browser is WebM and may be declared days later,
    // from a queue that has no idea what produced it.
    await store.put(sample('a').copyWith(audioFormat: 'webm'));

    expect((await store.load()).single.audioFormat, 'webm');
  });

  test('an entry written before formats existed reads back as m4a', () async {
    documents.contents['pending_captures.json'] =
        '[{"client_capture_id":"a","captured_at":"2026-06-10T08:00:00Z"}]';

    expect((await store.load()).single.audioFormat, 'm4a');
  });

  test('removing deletes the audio with the row', () async {
    blobs.blobs['a'] = _bytes();
    await store.put(sample('a'));

    await store.remove('a');

    expect(await store.load(), isEmpty);
    expect(await blobs.exists('a'), isFalse);
  });

  test('can keep the audio when the row goes', () async {
    blobs.blobs['a'] = _bytes();
    await store.put(sample('a'));

    await store.remove('a', deleteAudio: false);

    expect(await blobs.exists('a'), isTrue);
  });

  test('recovers from a truncated document instead of failing for good',
      () async {
    // An app killed mid-write leaves invalid JSON. Refusing to load would brick
    // the queue permanently — the one outcome an offline-first store cannot
    // have.
    documents.contents['pending_captures.json'] = '[{"client_';

    expect(await store.load(), isEmpty);
    await store.put(sample('a'));
    expect(await store.load(), hasLength(1));
  });

  test('drops rows that lost their required fields', () async {
    documents.contents['pending_captures.json'] = '[{"client_capture_id":"a"},'
        '{"client_capture_id":"b","captured_at":"2026-06-10T08:00:00Z"}]';

    final loaded = await store.load();
    expect(loaded, hasLength(1));
    expect(loaded.single.clientCaptureId, 'b');
  });
}

Uint8List _bytes() => Uint8List.fromList([1, 2, 3, 4]);
