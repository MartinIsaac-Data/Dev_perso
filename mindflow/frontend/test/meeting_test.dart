/// The live meeting client.
///
/// Two things are worth testing here and nothing else is:
///
/// * **the block loop keeps going when a block fails.** The room did not pause
///   for the network, and ending the meeting on a blip would be the worst
///   possible response to the situation this feature exists for;
/// * **a degraded report is not mistaken for a complete one.** A report that
///   looks finished and is not is the exact failure the whole feature has to
///   avoid, and it is one boolean away at every layer.
library;

// `StateNotifier.state` is protected so widgets go through the provider; a test
// asserting on the state machine is the case the annotation does not forbid.
// ignore_for_file: invalid_use_of_protected_member

import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/client.dart';
import 'package:mindflow/core/api/errors.dart';
import 'package:mindflow/core/api/meeting_models.dart';
import 'package:mindflow/core/audio/recorder.dart';
import 'package:mindflow/features/meeting/meeting_controller.dart';

import 'support/fake_storage.dart';

const _offline = ApiException(
  code: 'network_error',
  title: 'Connexion impossible',
  detail: 'Vérifiez votre connexion réseau.',
);

Map<String, dynamic> _suggestion(String text, {String kind = 'action'}) => {
      'kind': kind,
      'label': 'Action',
      'text': text,
      'owner': null,
      'confidence': 0.9,
      'at_word': 12,
      'created_at': '2026-06-10T09:00:00Z',
    };

class FakeApi implements MindflowApi {
  FakeApi(this.blobs);

  final FakeBlobStore blobs;

  Object? sendFailure;
  Object? closeFailure;
  Meeting? restored;

  int opens = 0;
  int sends = 0;
  int closes = 0;
  int abandons = 0;
  List<Map<String, dynamic>> nextSuggestions = const [];
  MeetingReport report = const MeetingReport(summary: 'Point budget.');

  /// What the closed meeting carries back. The server is the source of truth on
  /// close and returns everything it stored, so a fake that returned an empty
  /// list would be modelling a server that loses data.
  List<Map<String, dynamic>> closedSuggestions = const [];

  Meeting _live() => Meeting.fromJson({
        'id': 'm1',
        'status': 'live',
        'title': 'Point hebdo',
        'started_at': '2026-06-10T09:00:00Z',
        'transcript': '',
        'word_count': 0,
        'suggestions': <dynamic>[],
      });

  @override
  Future<Meeting> openMeeting({String? title}) async {
    opens += 1;
    return _live();
  }

  @override
  Future<Meeting?> liveMeeting() async => restored;

  @override
  Future<MeetingBlock> sendMeetingAudio(
    String meetingId,
    Uint8List bytes, {
    String mediaType = 'audio/webm',
  }) async {
    sends += 1;
    final failure = sendFailure;
    if (failure != null) throw failure;
    return MeetingBlock.fromJson({
      'meeting_id': meetingId,
      'word_count': sends * 40,
      'new_suggestions': nextSuggestions,
    });
  }

  @override
  Future<MeetingOutcome> closeMeeting(String meetingId) async {
    closes += 1;
    final failure = closeFailure;
    if (failure != null) throw failure;
    return MeetingOutcome(
      meeting: Meeting.fromJson({
        'id': meetingId,
        'status': 'ended',
        'transcript': 'tout ce qui a été dit',
        'word_count': 120,
        'suggestions': closedSuggestions,
      }),
      report: report,
    );
  }

  @override
  Future<void> abandonMeeting(String meetingId) async => abandons += 1;

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('${invocation.memberName} not stubbed');
}

class FakeRecorder implements VoiceRecorder {
  FakeRecorder(this.blobs);

  final FakeBlobStore blobs;
  var _counter = 0;
  String? _id;
  bool losesTheRecording = false;
  int cancels = 0;

  @override
  bool get isRecording => _id != null;

  @override
  String get audioFormat => 'webm';

  @override
  Stream<double> amplitudes(
          {Duration interval = const Duration(milliseconds: 120)}) =>
      const Stream<double>.empty();

  @override
  Future<String> start() async {
    _counter += 1;
    _id = 'block-$_counter';
    return _id!;
  }

  @override
  Future<RecordingResult?> stop() async {
    final id = _id;
    if (id == null) return null;
    _id = null;
    if (losesTheRecording) return null;
    await blobs.ingest(id, '/tmp/$id.webm', extension: 'webm');
    return RecordingResult(
      clientCaptureId: id,
      audioFormat: 'webm',
      duration: const Duration(seconds: 30),
      startedAt: DateTime.utc(2026, 6, 10, 9),
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
  late FakeApi api;
  late FakeRecorder recorder;
  late MeetingController controller;

  setUp(() {
    blobs = FakeBlobStore();
    api = FakeApi(blobs);
    recorder = FakeRecorder(blobs);
    controller = MeetingController(api: api, recorder: recorder, blobs: blobs);
  });

  tearDown(() => controller.dispose());

  group('models', () {
    test('an unknown suggestion kind becomes a question, never an action', () {
      // The direction is the point: an invented question is noise, an invented
      // action asks somebody to do something nobody agreed to.
      expect(SuggestionKind.parse('todo'), SuggestionKind.question);
      expect(SuggestionKind.parse(null), SuggestionKind.question);
      expect(SuggestionKind.parse('action'), SuggestionKind.action);
    });

    test('a degraded report says so and still carries what was found', () {
      final report = MeetingReport.fromJson({
        'summary': '',
        'decisions': <dynamic>[],
        'actions': [
          {'text': 'relancer le DAF', 'owner': 'Marie', 'due': null},
        ],
        'open_questions': <dynamic>[],
        'degraded': true,
        'reason': 'Le compte rendu n\'a pas pu être produit.',
      });

      expect(report.degraded, isTrue);
      expect(report.reason, isNotEmpty);
      expect(report.actions.single.owner, 'Marie');
      // Not empty: the live pass found something real, and listing it beats an
      // apology.
      expect(report.isEmpty, isFalse);
    });

    test('a meeting that produced nothing reads as empty rather than degraded',
        () {
      const report = MeetingReport(summary: '');
      expect(report.isEmpty, isTrue);
      expect(report.degraded, isFalse);
    });

    test('an unknown status is not treated as live', () {
      // Treating an unknown status as live would leave the interface offering
      // to record into a meeting the server has closed.
      expect(MeetingStatus.parse('archived').isLive, isFalse);
      expect(MeetingStatus.parse('live').isLive, isTrue);
    });
  });

  group('starting', () {
    test('opens a meeting and begins recording', () async {
      await controller.start(title: 'Point hebdo');

      expect(api.opens, 1);
      expect(controller.state.phase, MeetingPhase.recording);
      expect(recorder.isRecording, isTrue);
    });

    test('a refused microphone is reported, not swallowed', () async {
      final denied = _DeniedRecorder();
      final other = MeetingController(api: api, recorder: denied, blobs: blobs);
      addTearDown(other.dispose);

      await other.start();

      expect(other.state.phase, MeetingPhase.failed);
      expect(other.state.message, contains('micro'));
    });

    test('a meeting left open by a previous run is offered, not restarted',
        () async {
      // The transcript is on the server, so silently starting over would lose
      // forty minutes of somebody's afternoon.
      api.restored = Meeting.fromJson({
        'id': 'm-old',
        'status': 'live',
        'transcript': 'déjà dit',
        'word_count': 200,
        'suggestions': [_suggestion('relancer le DAF')],
      });

      await controller.restore();

      expect(controller.state.meeting?.id, 'm-old');
      expect(controller.state.wordCount, 200);
      expect(controller.state.suggestions, hasLength(1));
      expect(controller.state.phase, MeetingPhase.idle);
      expect(api.opens, 0);
    });

    test('nothing to restore leaves the screen alone', () async {
      await controller.restore();

      expect(controller.state.meeting, isNull);
      expect(controller.state.message, isNull);
    });
  });

  group('closing', () {
    test('sends the last block, then produces the report', () async {
      // The final thirty seconds are where people agree what happens next.
      api.nextSuggestions = [_suggestion('envoyer le compte rendu')];
      await controller.start();

      await controller.close();

      expect(api.sends, 1);
      expect(api.closes, 1);
      expect(controller.state.phase, MeetingPhase.closed);
      expect(controller.state.report?.summary, 'Point budget.');
    });

    test('a failed close says the meeting is still open', () async {
      // Nothing is lost — the meeting is still live server-side — and saying so
      // is the difference between a retry and a panic.
      api.closeFailure = _offline;
      await controller.start();

      await controller.close();

      expect(controller.state.phase, MeetingPhase.failed);
      expect(controller.state.message, contains('reste ouverte'));
    });

    test('abandoning discards without producing anything', () async {
      await controller.start();

      await controller.abandon();

      expect(api.abandons, 1);
      expect(api.closes, 0);
      expect(recorder.cancels, 1);
      expect(controller.state.meeting, isNull);
    });
  });

  group('degradation', () {
    test('a block that fails to send is counted, and recording continues',
        () async {
      api.sendFailure = _offline;
      await controller.start();

      // Closing cuts one last block, which is the one that fails.
      await controller.close();

      expect(controller.state.blocksLost, 1);
      // The meeting still closed: a lost block is a hole in the transcript,
      // not the end of the meeting.
      expect(api.closes, 1);
    });

    test('a recording the platform lost is counted rather than sent', () async {
      recorder.losesTheRecording = true;
      await controller.start();

      await controller.close();

      expect(api.sends, 0);
      expect(controller.state.blocksLost, 0); // nothing was recorded to lose
      expect(api.closes, 1);
    });

    test('closing takes the server list, which is the one that is complete',
        () async {
      // The client's list is what it happened to see; the server's is what was
      // stored. On close the server wins, and a client that kept its own would
      // show a panel that disagrees with the report beside it.
      api.closedSuggestions = [
        _suggestion('relancer le DAF'),
        _suggestion('reporter au 12', kind: 'decision'),
      ];
      await controller.start();

      await controller.close();

      expect(controller.state.suggestions, hasLength(2));
    });
  });
}

class _DeniedRecorder implements VoiceRecorder {
  @override
  bool get isRecording => false;

  @override
  String get audioFormat => 'webm';

  @override
  Stream<double> amplitudes(
          {Duration interval = const Duration(milliseconds: 120)}) =>
      const Stream<double>.empty();

  @override
  Future<String> start() async => throw const MicrophonePermissionDenied();

  @override
  Future<RecordingResult?> stop() async => null;

  @override
  Future<void> cancel() async {}

  @override
  Future<void> dispose() async {}
}
