// `StateNotifier.state` is protected so widgets go through the provider. A test
// asserting on the state machine is precisely the case the annotation does not
// mean to forbid.
// ignore_for_file: invalid_use_of_protected_member

import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/client.dart';
import 'package:mindflow/core/api/errors.dart';
import 'package:mindflow/core/api/models.dart';
import 'package:mindflow/core/audio/recorder.dart';
import 'package:mindflow/core/time/device_timezone.dart';
import 'package:mindflow/features/capture/capture_controller.dart';
import 'package:mindflow/features/capture/pending_capture_store.dart';

import 'support/fake_storage.dart';

/// What the client raises when a request never reached the server. Built by the
/// API client's interceptor from a Dio transport failure; here it stands in for
/// a phone in a tunnel.
const _offline = ApiException(
  code: 'network_error',
  title: 'Connexion impossible',
  detail: 'Vérifiez votre connexion réseau.',
);

/// Only the calls the capture path makes are implemented; anything else is a
/// test that reached further than it meant to, and should say so loudly.
class FakeApi implements MindflowApi {
  FakeApi({this.declareFailure, this.completeFailure});

  Object? declareFailure;
  Object? completeFailure;

  int declareCalls = 0;
  final declaredFormats = <String>[];
  int uploadCalls = 0;
  int completeCalls = 0;
  String? quotaWarning;
  CaptureStatus finalStatus = CaptureStatus.completed;
  bool withUploadUrl = true;
  final declaredIds = <String>[];

  @override
  Future<DeclaredCapture> declareCapture({
    required String clientCaptureId,
    required int durationMs,
    required DateTime capturedAt,
    required String timezone,
    String audioFormat = 'm4a',
    int? audioBytes,
    String? languageHint,
    String source = 'app',
  }) async {
    declareCalls += 1;
    declaredIds.add(clientCaptureId);
    declaredFormats.add(audioFormat);
    final failure = declareFailure;
    if (failure != null) throw failure;
    return DeclaredCapture(
      id: 'server-$clientCaptureId',
      uploadUrl: withUploadUrl ? 'https://storage.test/put' : null,
      uploadHeaders: const {'content-type': 'audio/mp4'},
      quotaWarning: quotaWarning,
    );
  }

  @override
  Future<void> uploadAudio({
    required String url,
    required Uint8List bytes,
    required Map<String, String> headers,
  }) async {
    uploadCalls += 1;
  }

  @override
  Future<Capture> completeCapture(String captureId) async {
    completeCalls += 1;
    final failure = completeFailure;
    if (failure != null) throw failure;
    return _capture(captureId, CaptureStatus.uploaded);
  }

  @override
  Future<Capture> getCapture(String captureId) async =>
      _capture(captureId, finalStatus);

  Capture _capture(String id, CaptureStatus status) => Capture(
        id: id,
        status: status,
        durationMs: 4200,
        capturedAt: DateTime.utc(2026, 6, 10, 8),
      );

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('${invocation.memberName} not stubbed');
}

class FakeRecorder implements VoiceRecorder {
  FakeRecorder(this.blobs);

  final FakeBlobStore blobs;
  String? _id;
  Duration duration = const Duration(seconds: 4);
  int cancels = 0;
  var _counter = 0;

  /// Set to model a platform that handed back nothing storable — a permission
  /// revoked mid-recording, or a browser tab that lost its blob.
  bool losesTheRecording = false;

  @override
  bool get isRecording => _id != null;

  @override
  String get audioFormat => 'm4a';

  @override
  Stream<double> amplitudes(
          {Duration interval = const Duration(milliseconds: 120)}) =>
      const Stream<double>.empty();

  @override
  Future<String> start() async {
    _counter += 1;
    _id = 'client-$_counter';
    return _id!;
  }

  @override
  Future<RecordingResult?> stop() async {
    final id = _id;
    if (id == null) return null;
    _id = null;
    if (losesTheRecording) return null;
    // A real recorder stores the bytes before returning, because the caller's
    // next act is to queue an entry pointing at them.
    await blobs.ingest(id, '/tmp/$id.m4a', extension: 'm4a');
    return RecordingResult(
      clientCaptureId: id,
      audioFormat: 'm4a',
      duration: duration,
      startedAt: DateTime.utc(2026, 6, 10, 8),
    );
  }

  @override
  Future<void> cancel() async {
    cancels += 1;
    _id = null;
  }

  @override
  Future<void> dispose() async {}
}

void main() {
  late FakeBlobStore blobs;
  late FakeDocumentStore documents;
  late FakeApi api;
  late FakeRecorder recorder;
  late PendingCaptureStore store;
  late CaptureController controller;

  setUp(() {
    blobs = FakeBlobStore();
    documents = FakeDocumentStore();
    api = FakeApi();
    recorder = FakeRecorder(blobs);
    store = PendingCaptureStore(documents: documents, blobs: blobs);
    controller = CaptureController(
      api: api,
      recorder: recorder,
      store: store,
      timezone: DeviceTimezone(resolve: () async => 'Europe/Paris'),
      blobs: blobs,
    );
  });

  tearDown(() => controller.dispose());

  test('runs declare, upload and complete in order, then polls', () async {
    await controller.startRecording();
    await controller.stopAndSend();

    expect(api.declareCalls, 1);
    expect(api.uploadCalls, 1);
    expect(api.completeCalls, 1);
    expect(controller.state.phase, CapturePhase.done);
    expect(controller.state.capture?.status, CaptureStatus.completed);
    // Accepted by the server: nothing left queued on the device.
    expect(await store.load(), isEmpty);
  });

  test('does not send a recording shorter than the floor', () async {
    recorder.duration = const Duration(milliseconds: 200);

    await controller.startRecording();
    await controller.stopAndSend();

    expect(api.declareCalls, 0);
    expect(controller.state.phase, CapturePhase.idle);
    expect(controller.state.message, contains('trop court'));
  });

  test('keeps the capture on the device when the network is down', () async {
    api.declareFailure = _offline;

    await controller.startRecording();
    await controller.stopAndSend();

    expect(controller.state.phase, CapturePhase.failed);
    // Says "pas de réseau", not "l'envoi a échoué": nothing was lost, and the
    // message has to say so or the user re-records.
    expect(controller.state.message, contains('Pas de réseau'));
    final queued = await store.load();
    expect(queued, hasLength(1));
    // The audio is still there — that is the whole point (ADR-009).
    expect(await blobs.exists(queued.single.clientCaptureId), isTrue);
    expect(queued.single.attempts, 1);
  });

  test('flushPending replays the same client id, never a new one', () async {
    api.declareFailure = _offline;
    await controller.startRecording();
    await controller.stopAndSend();

    api.declareFailure = null;
    await controller.flushPending();

    expect(api.declaredIds, ['client-1', 'client-1']);
    expect(controller.state.phase, CapturePhase.done);
    expect(await store.load(), isEmpty);
  });

  test('a replay with no upload URL skips the upload and still completes',
      () async {
    // The server already holds the audio; re-uploading it would be wasted
    // bytes on a connection that just proved itself unreliable.
    api.withUploadUrl = false;

    await controller.startRecording();
    await controller.stopAndSend();

    expect(api.uploadCalls, 0);
    expect(api.completeCalls, 1);
    expect(controller.state.phase, CapturePhase.done);
  });

  test('surfaces the quota warning without treating it as a failure', () async {
    api.quotaWarning = 'Quota mensuel atteint.';
    api.finalStatus = CaptureStatus.partiallyProcessed;

    await controller.startRecording();
    await controller.stopAndSend();

    expect(controller.state.phase, CapturePhase.done);
    expect(controller.state.quotaWarning, 'Quota mensuel atteint.');
  });

  test('a failed transcription is a terminal state, not an error state',
      () async {
    api.finalStatus = CaptureStatus.transcriptionFailed;

    await controller.startRecording();
    await controller.stopAndSend();

    expect(controller.state.phase, CapturePhase.done);
    expect(controller.state.message, contains('audio est conservé'));
  });

  test('an auth failure is not queued for retry', () async {
    // Retrying an expired-token upload in a loop achieves nothing; the user has
    // to sign in again first.
    api.declareFailure = const ApiException(
      code: 'token_expired',
      title: 'Jeton expiré',
      detail: 'expired',
      status: 401,
    );

    await controller.startRecording();
    await controller.stopAndSend();

    expect(controller.state.phase, CapturePhase.failed);
    final queued = await store.load();
    expect(queued.single.attempts, 0);
  });

  test('drops a queued capture whose audio vanished', () async {
    api.declareFailure = _offline;
    await controller.startRecording();
    await controller.stopAndSend();

    final queued = await store.load();
    await blobs.delete(queued.single.clientCaptureId);

    api.declareFailure = null;
    await controller.flushPending();

    expect(api.declareCalls, 1); // only the original, failed attempt
    expect(await store.load(), isEmpty);
  });

  test('declares the format the recording was actually made in', () async {
    // A browser records WebM. Declaring m4a would make the server store the
    // bytes under a name that says the wrong thing, and the transcriber read
    // it accordingly.
    await controller.startRecording();
    await controller.stopAndSend();

    expect(api.declaredFormats, ['m4a']);
  });

  test('a recording the platform lost is reported, not queued', () async {
    recorder.losesTheRecording = true;

    await controller.startRecording();
    await controller.stopAndSend();

    expect(controller.state.phase, CapturePhase.failed);
    expect(await store.load(), isEmpty);
    expect(api.declareCalls, 0);
  });

  test('cancelling stops the recorder and clears the state', () async {
    await controller.startRecording();
    expect(controller.state.isRecording, isTrue);

    await controller.cancelRecording();

    expect(recorder.cancels, 1);
    expect(controller.state.phase, CapturePhase.idle);
    expect(api.declareCalls, 0);
  });
}
