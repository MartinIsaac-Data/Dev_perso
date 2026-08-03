import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/features/capture/pending_capture_store.dart';

void main() {
  late Directory directory;
  late PendingCaptureStore store;

  setUp(() {
    directory = Directory.systemTemp.createTempSync('mindflow_pending');
    store = PendingCaptureStore(directory: directory);
  });

  tearDown(() {
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  PendingCapture sample(String id) => PendingCapture(
        clientCaptureId: id,
        filePath: '${directory.path}/$id.m4a',
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

  test('removing deletes the audio file with the row', () async {
    final capture = sample('a');
    File(capture.filePath).writeAsStringSync('audio');
    await store.put(capture);

    await store.remove('a');

    expect(await store.load(), isEmpty);
    expect(File(capture.filePath).existsSync(), isFalse);
  });

  test('can keep the file when the row goes', () async {
    final capture = sample('a');
    File(capture.filePath).writeAsStringSync('audio');
    await store.put(capture);

    await store.remove('a', deleteFile: false);

    expect(File(capture.filePath).existsSync(), isTrue);
  });

  test('recovers from a truncated file instead of failing for good', () async {
    // An app killed mid-write leaves invalid JSON. Refusing to load would brick
    // the queue permanently — the one outcome an offline-first store cannot
    // have.
    File('${directory.path}/pending_captures.json')
        .writeAsStringSync('[{"client_');

    expect(await store.load(), isEmpty);
    await store.put(sample('a'));
    expect(await store.load(), hasLength(1));
  });

  test('drops rows that lost their required fields', () async {
    File('${directory.path}/pending_captures.json').writeAsStringSync(
      '[{"client_capture_id":"a"},'
      '{"client_capture_id":"b","file_path":"/tmp/b.m4a",'
      '"captured_at":"2026-06-10T08:00:00Z"}]',
    );

    final loaded = await store.load();
    expect(loaded, hasLength(1));
    expect(loaded.single.clientCaptureId, 'b');
  });
}
