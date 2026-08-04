/// HTTP client for the MindFlow API.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'assistant_models.dart';
import 'enterprise_models.dart';
import 'errors.dart';
import 'models.dart';
import 'planning_models.dart';

/// Injected at build time: `--dart-define=MINDFLOW_API_BASE_URL=...`
const kApiBaseUrl = String.fromEnvironment(
  'MINDFLOW_API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);

typedef TokenProvider = Future<String?> Function();

class MindflowApi {
  MindflowApi({required TokenProvider tokenProvider, Dio? dio})
      : _tokenProvider = tokenProvider,
        _dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: kApiBaseUrl,
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 30),
                headers: {'accept': 'application/json'},
                // Errors are decoded from the problem document, so let every
                // status through rather than having Dio throw on 4xx.
                validateStatus: (status) => status != null && status < 500,
              ),
            ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _tokenProvider();
          if (token != null) {
            options.headers['authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      ),
    );
  }

  final Dio _dio;
  final TokenProvider _tokenProvider;

  Future<Map<String, dynamic>> _get(String path,
      {Map<String, dynamic>? query}) async {
    final response =
        await _dio.get<Map<String, dynamic>>(path, queryParameters: query);
    return _unwrap(response);
  }

  Future<Map<String, dynamic>> _post(String path, {Object? body}) async {
    final response = await _dio.post<Map<String, dynamic>>(path, data: body);
    return _unwrap(response);
  }

  Future<Map<String, dynamic>> _patch(String path, {Object? body}) async {
    final response = await _dio.patch<Map<String, dynamic>>(path, data: body);
    return _unwrap(response);
  }

  /// Deletes answer `204` with no body, so there is nothing to unwrap on
  /// success — but a failure still carries a problem document, and dropping it
  /// would turn "you are not allowed to do that" into a silent no-op.
  Future<void> _delete(String path) async {
    final response = await _dio.delete<Map<String, dynamic>>(path);
    if ((response.statusCode ?? 500) >= 400) _unwrap(response);
  }

  Map<String, dynamic> _unwrap(Response<Map<String, dynamic>> response) {
    final data = response.data ?? const <String, dynamic>{};
    if ((response.statusCode ?? 500) >= 400) {
      throw ApiException(
        code: (data['code'] as String?) ?? 'internal_error',
        title: (data['title'] as String?) ?? 'Erreur',
        detail: (data['detail'] as String?) ?? 'Une erreur est survenue.',
        status: response.statusCode,
        requestId: data['request_id'] as String?,
        currentVersion: (data['current_version'] as num?)?.toInt(),
      );
    }
    return data;
  }

  // -- Captures -----------------------------------------------------------

  /// Declare a capture and obtain a signed upload URL.
  ///
  /// [clientCaptureId] is generated on the device *before* recording: replaying
  /// this call after a lost response returns the same capture instead of
  /// creating a duplicate (ADR-009).
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
    final data = await _post(
      '/v1/captures',
      body: {
        'client_capture_id': clientCaptureId,
        'kind': 'quick',
        'duration_ms': durationMs,
        'audio_format': audioFormat,
        if (audioBytes != null) 'audio_bytes': audioBytes,
        'captured_at': capturedAt.toUtc().toIso8601String(),
        'capture_timezone': timezone,
        'source': source,
        if (languageHint != null) 'language_hint': languageHint,
      },
    );
    return DeclaredCapture.fromJson(data['data'] as Map<String, dynamic>);
  }

  /// Upload the audio straight to storage. It never transits the API (ADR-018).
  Future<void> uploadAudio({
    required String url,
    required Uint8List bytes,
    required Map<String, String> headers,
  }) async {
    final response = await Dio().putUri<void>(
      Uri.parse(url),
      data: Stream.fromIterable([bytes]),
      options: Options(
        headers: {...headers, 'content-length': bytes.length},
        validateStatus: (status) => status != null && status < 500,
      ),
    );
    final status = response.statusCode ?? 500;
    if (status >= 400) {
      throw ApiException(
        code: 'upload_failed',
        title: 'Envoi impossible',
        detail: "L'envoi de l'audio a échoué (HTTP $status).",
        status: status,
      );
    }
  }

  Future<Capture> completeCapture(String captureId) async {
    final data = await _post('/v1/captures/$captureId/complete');
    return Capture.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Capture> getCapture(String captureId) async {
    final data = await _get('/v1/captures/$captureId');
    return Capture.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<Capture>> listCaptures({int limit = 50}) async {
    final data = await _get('/v1/captures', query: {'limit': limit});
    return ((data['data'] as List<dynamic>?) ?? const [])
        .map((e) => Capture.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> deleteCapture(String captureId, {bool cascade = false}) async {
    await _dio.delete<void>(
      '/v1/captures/$captureId',
      queryParameters: {'cascade': cascade},
    );
  }

  // -- Entries ------------------------------------------------------------

  Future<List<Entry>> listEntries({
    String? entryType,
    String? status,
    String? search,
    int limit = 100,
  }) async {
    final data = await _get(
      '/v1/entries',
      query: {
        if (entryType != null) 'entry_type': entryType,
        if (status != null) 'status': status,
        if (search != null && search.isNotEmpty) 'q': search,
        'limit': limit,
      },
    );
    return ((data['data'] as List<dynamic>?) ?? const [])
        .map((e) => Entry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Entry> getEntry(String entryId) async {
    final data = await _get('/v1/entries/$entryId');
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  /// Partial update with optimistic locking.
  ///
  /// [expectedVersion] is sent as `If-Match`; a 409 carries the server state so
  /// the caller can merge rather than pick a winner (API.md §8.2).
  Future<Entry> updateEntry(
    String entryId,
    Map<String, dynamic> changes, {
    int? expectedVersion,
  }) async {
    final response = await _dio.patch<Map<String, dynamic>>(
      '/v1/entries/$entryId',
      data: changes,
      options: Options(
        headers: {
          if (expectedVersion != null) 'If-Match': '"$expectedVersion"'
        },
      ),
    );
    return Entry.fromJson(_unwrap(response)['data'] as Map<String, dynamic>);
  }

  Future<Entry> completeEntry(String entryId) async {
    final data = await _post('/v1/entries/$entryId/complete');
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Entry> createEntry({
    required String title,
    String entryType = 'note',
    String? body,
    String? dueExpression,
  }) async {
    final data = await _post(
      '/v1/entries',
      body: {
        'entry_type': entryType,
        'title': title,
        if (body != null) 'body': body,
        if (dueExpression != null) 'due_expression': dueExpression,
      },
    );
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> deleteEntry(String entryId) async {
    await _dio.delete<void>('/v1/entries/$entryId');
  }

  // -- Dashboard ----------------------------------------------------------

  Future<Dashboard> dashboard() async {
    final data = await _get('/v1/dashboard');
    return Dashboard.fromJson(data['data'] as Map<String, dynamic>);
  }

  // -- Planning (Phase 2) -------------------------------------------------

  Future<Agenda> agenda({
    AgendaView view = AgendaView.week,
    DateTime? anchor,
    bool includeDone = true,
    bool includeUnscheduled = false,
    String? projectId,
  }) async {
    final data = await _get('/v1/agenda', query: {
      'view': view.param,
      if (anchor != null) 'anchor': _day(anchor),
      'include_done': includeDone,
      'include_unscheduled': includeUnscheduled,
      if (projectId != null) 'project_id': projectId,
    });
    return Agenda.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<CalendarMonth> calendar({DateTime? month}) async {
    final data = await _get('/v1/calendar', query: {
      if (month != null) 'month': _day(month),
    });
    return CalendarMonth.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<Subtask>> listSubtasks(String entryId) async {
    final data = await _get('/v1/entries/$entryId/subtasks');
    return _list(data, Subtask.fromJson);
  }

  Future<Subtask> addSubtask(String entryId, String title) async {
    final data =
        await _post('/v1/entries/$entryId/subtasks', body: {'title': title});
    return Subtask.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Subtask> updateSubtask(
    String subtaskId, {
    String? title,
    bool? completed,
  }) async {
    final response = await _dio.patch<Map<String, dynamic>>(
      '/v1/subtasks/$subtaskId',
      data: {
        if (title != null) 'title': title,
        if (completed != null) 'completed': completed,
      },
    );
    return Subtask.fromJson(_unwrap(response)['data'] as Map<String, dynamic>);
  }

  Future<void> deleteSubtask(String subtaskId) async {
    await _dio.delete<void>('/v1/subtasks/$subtaskId');
  }

  /// Sends the full ordered list rather than a (from, to) pair, which makes the
  /// call idempotent — drag-and-drop on a flaky link emits deltas out of order.
  Future<List<Subtask>> reorderSubtasks(
      String entryId, List<String> orderedIds) async {
    final data = await _post(
      '/v1/entries/$entryId/subtasks/reorder',
      body: {'ordered_ids': orderedIds},
    );
    return _list(data, Subtask.fromJson);
  }

  /// Completing a recurring task returns the occurrence it generated, so the
  /// interface can say "next: Monday" at the moment the user is looking.
  Future<(Entry, Entry?)> completeTask(String entryId) async {
    final data = await _post('/v1/entries/$entryId/complete-task');
    final body = data['data'] as Map<String, dynamic>;
    return (
      Entry.fromJson(body['entry'] as Map<String, dynamic>),
      body['next_occurrence'] == null
          ? null
          : Entry.fromJson(body['next_occurrence'] as Map<String, dynamic>),
    );
  }

  Future<Entry> reopenTask(String entryId) async {
    final data = await _post('/v1/entries/$entryId/reopen');
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Entry> snoozeTask(String entryId, DateTime until) async {
    final data = await _post(
      '/v1/entries/$entryId/snooze',
      body: {'until': until.toUtc().toIso8601String()},
    );
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Entry> rescheduleTask(String entryId, DateTime? dueAt) async {
    final data = await _post(
      '/v1/entries/$entryId/reschedule',
      body: {'due_at': dueAt?.toUtc().toIso8601String()},
    );
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Entry> setRecurrence(String entryId, String? rule) async {
    final data =
        await _post('/v1/entries/$entryId/recurrence', body: {'rule': rule});
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Entry> pinEntry(String entryId, {required bool pinned}) async {
    final data =
        await _post('/v1/entries/$entryId/pin', body: {'pinned': pinned});
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<int> bulkUpdate(
    List<String> ids, {
    String? status,
    String? priority,
    String? projectId,
    bool clearProject = false,
  }) async {
    final data = await _post('/v1/entries/bulk', body: {
      'ids': ids,
      if (status != null) 'status': status,
      if (priority != null) 'priority': priority,
      if (projectId != null) 'project_id': projectId,
      'clear_project': clearProject,
    });
    return ((data['data'] as Map<String, dynamic>)['matched'] as num).toInt();
  }

  // -- Reminders and notifications ----------------------------------------

  Future<List<Reminder>> listReminders({String? entryId}) async {
    final data = await _get('/v1/reminders', query: {
      if (entryId != null) 'entry_id': entryId,
    });
    return _list(data, Reminder.fromJson);
  }

  Future<Reminder> createReminder({
    String? entryId,
    DateTime? remindAt,
    String? offsetRule,
    String channel = 'push',
  }) async {
    final data = await _post('/v1/reminders', body: {
      if (entryId != null) 'entry_id': entryId,
      if (remindAt != null) 'remind_at': remindAt.toUtc().toIso8601String(),
      if (offsetRule != null) 'offset_rule': offsetRule,
      'channel': channel,
    });
    return Reminder.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> cancelReminder(String reminderId) async {
    await _dio.delete<void>('/v1/reminders/$reminderId');
  }

  Future<NotificationCentre> notifications(
      {bool unreadOnly = false, int limit = 50}) async {
    final data = await _get('/v1/notifications', query: {
      'unread_only': unreadOnly,
      'limit': limit,
    });
    return NotificationCentre.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> markNotificationRead(String notificationId) async {
    await _post('/v1/notifications/$notificationId/read');
  }

  Future<void> markAllNotificationsRead() async {
    await _post('/v1/notifications/read-all');
  }

  /// Idempotent on `installId`. Keyed on the installation rather than the push
  /// token because tokens rotate — keying on one sends the same reminder five
  /// times to a single phone.
  Future<RegisteredDevice> registerDevice({
    required String installId,
    required String platform,
    required String pushProvider,
    String? pushToken,
    String? name,
    String? appVersion,
    String? osVersion,
  }) async {
    final response = await _dio.put<Map<String, dynamic>>('/v1/devices', data: {
      'install_id': installId,
      'platform': platform,
      'push_provider': pushProvider,
      if (pushToken != null) 'push_token': pushToken,
      if (name != null) 'name': name,
      if (appVersion != null) 'app_version': appVersion,
      if (osVersion != null) 'os_version': osVersion,
    });
    return RegisteredDevice.fromJson(
      _unwrap(response)['data'] as Map<String, dynamic>,
    );
  }

  Future<List<RegisteredDevice>> listDevices() async {
    final data = await _get('/v1/devices');
    return _list(data, RegisteredDevice.fromJson);
  }

  // -- Search, statistics, history, library --------------------------------

  Future<SearchResults> search(String query,
      {int limit = 50, int offset = 0}) async {
    final data = await _get('/v1/search', query: {
      'q': query,
      'limit': limit,
      'offset': offset,
    });
    return SearchResults.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<QuickResults> quickSearch(String query) async {
    final data = await _get('/v1/search/quick', query: {'q': query});
    return QuickResults.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Statistics> statistics({int windowDays = 30}) async {
    final data = await _get('/v1/stats', query: {'window_days': windowDays});
    return Statistics.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<ActivityEvent>> activity({
    String? entryId,
    String? projectId,
    int limit = 50,
  }) async {
    final data = await _get('/v1/activity', query: {
      if (entryId != null) 'entry_id': entryId,
      if (projectId != null) 'project_id': projectId,
      'limit': limit,
    });
    return _list(data, ActivityEvent.fromJson);
  }

  Future<List<Tag>> listTags() async {
    final data = await _get('/v1/tags');
    return _list(data, Tag.fromJson);
  }

  Future<Tag> updateTag(String tagId,
      {String? label, String? color, bool? pinned}) async {
    final response = await _dio.patch<Map<String, dynamic>>(
      '/v1/tags/$tagId',
      data: {
        if (label != null) 'label': label,
        if (color != null) 'color': color,
        if (pinned != null) 'pinned': pinned,
      },
    );
    return Tag.fromJson(_unwrap(response)['data'] as Map<String, dynamic>);
  }

  Future<void> deleteTag(String tagId) async {
    await _dio.delete<void>('/v1/tags/$tagId');
  }

  Future<List<Tag>> attachTags(String entryId, List<String> labels) async {
    final data =
        await _post('/v1/entries/$entryId/tags', body: {'labels': labels});
    return _list(data, Tag.fromJson);
  }

  Future<void> detachTag(String entryId, String tagId) async {
    await _dio.delete<void>('/v1/entries/$entryId/tags/$tagId');
  }

  Future<List<SavedFilter>> listFilters() async {
    final data = await _get('/v1/filters');
    return _list(data, SavedFilter.fromJson);
  }

  Future<SavedFilter> createFilter({
    required String name,
    required String query,
    String? icon,
    bool pinned = false,
  }) async {
    final data = await _post('/v1/filters', body: {
      'name': name,
      'query': query,
      if (icon != null) 'icon': icon,
      'pinned': pinned,
    });
    return SavedFilter.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> deleteFilter(String filterId) async {
    await _dio.delete<void>('/v1/filters/$filterId');
  }

  Future<List<ProjectDetail>> listProjectsDetailed(
      {bool includeArchived = false}) async {
    final data = await _get('/v1/projects/detailed', query: {
      'include_archived': includeArchived,
    });
    return _list(data, ProjectDetail.fromJson);
  }

  Future<ProjectDetail> updateProject(
    String projectId, {
    String? name,
    String? description,
    String? color,
    bool? pinned,
    bool? archived,
  }) async {
    final response = await _dio.patch<Map<String, dynamic>>(
      '/v1/projects/$projectId',
      data: {
        if (name != null) 'name': name,
        if (description != null) 'description': description,
        if (color != null) 'color': color,
        if (pinned != null) 'pinned': pinned,
        if (archived != null) 'archived': archived,
      },
    );
    return ProjectDetail.fromJson(
        _unwrap(response)['data'] as Map<String, dynamic>);
  }

  // -- Assistant, semantic search, entities, digests, memory (Phase 3) -----

  /// Ask the assistant. [clientMessageId] makes a retry idempotent: a phone on
  /// a flaky connection must not ask — or be billed — twice (ADR-009).
  Future<Answer> ask(
    String question, {
    String? conversationId,
    String? clientMessageId,
  }) async {
    final data = await _post('/v1/assistant/chat', body: {
      'question': question,
      if (conversationId != null) 'conversation_id': conversationId,
      if (clientMessageId != null) 'client_message_id': clientMessageId,
    });
    return Answer.fromJson(data['data'] as Map<String, dynamic>);
  }

  /// Ask, receiving the answer as it is written.
  ///
  /// Yields text fragments, then one final [Answer] carrying the citations. A
  /// caller that only wants the finished answer can ignore every fragment and
  /// take the last event — which is exactly what [ask] does over one round
  /// trip, so the two paths never diverge.
  Stream<AssistantEvent> askStreaming(
    String question, {
    String? conversationId,
    String? clientMessageId,
  }) async* {
    final response = await _dio.post<ResponseBody>(
      '/v1/assistant/chat/stream',
      data: {
        'question': question,
        if (conversationId != null) 'conversation_id': conversationId,
        if (clientMessageId != null) 'client_message_id': clientMessageId,
      },
      options: Options(responseType: ResponseType.stream, headers: {
        'accept': 'text/event-stream',
      }),
    );

    final body = response.data;
    if (body == null) return;

    // Server-sent events arrive split across arbitrary chunk boundaries, so a
    // buffer is not optional: parsing each chunk on its own would truncate
    // every event that happens to straddle two packets.
    var buffer = '';
    await for (final chunk in body.stream) {
      buffer += utf8.decode(chunk, allowMalformed: true);
      while (true) {
        final split = buffer.indexOf('\n\n');
        if (split < 0) break;
        final frame = buffer.substring(0, split);
        buffer = buffer.substring(split + 2);

        final event = _parseEvent(frame);
        if (event != null) yield event;
      }
    }
  }

  AssistantEvent? _parseEvent(String frame) {
    String? name;
    final payload = StringBuffer();
    for (final line in frame.split('\n')) {
      if (line.startsWith('event: ')) {
        name = line.substring(7).trim();
      } else if (line.startsWith('data: ')) {
        payload.write(line.substring(6));
      }
    }
    if (name == null || payload.isEmpty) return null;

    final decoded = jsonDecode(payload.toString());
    if (name == 'delta') {
      return AssistantEvent.delta(asMap(decoded)['text'] as String? ?? '');
    }
    if (name == 'answer') {
      return AssistantEvent.done(Answer.fromJson(asMap(decoded)));
    }
    return null;
  }

  Future<List<Conversation>> listConversations() async {
    final data = await _get('/v1/assistant/conversations');
    return _list(data, Conversation.fromJson);
  }

  Future<List<ChatMessage>> conversationMessages(String conversationId) async {
    final data = await _get('/v1/assistant/conversations/$conversationId');
    return _list(data, ChatMessage.fromJson);
  }

  Future<SemanticResults> semanticSearch(
    String query, {
    int limit = 10,
    List<String> entryTypes = const [],
  }) async {
    final data = await _post('/v1/search/semantic', body: {
      'query': query,
      'limit': limit,
      if (entryTypes.isNotEmpty) 'entry_types': entryTypes,
    });
    return SemanticResults.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<IndexStatus> indexStatus() async {
    final data = await _get('/v1/search/index-status');
    return IndexStatus.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<KnownEntity>> listEntities(
      {EntityKind? kind, String? query}) async {
    final data = await _get('/v1/entities', query: {
      if (kind != null) 'kind': kind.param,
      if (query != null && query.isNotEmpty) 'q': query,
    });
    return _list(data, KnownEntity.fromJson);
  }

  Future<List<RecurringTheme>> themes({int days = 90}) async {
    final data = await _get('/v1/entities/themes', query: {'days': days});
    return _list(data, RecurringTheme.fromJson);
  }

  Future<List<Digest>> listDigests({DigestPeriod? period}) async {
    final data = await _get('/v1/digests', query: {
      if (period != null) 'period': period.param,
    });
    return _list(data, Digest.fromJson);
  }

  Future<Digest> generateDigest(DigestPeriod period,
      {bool force = false}) async {
    final data = await _post('/v1/digests',
        body: {'period': period.param, if (force) 'force': true});
    return Digest.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Digest> markDigestRead(String digestId) async {
    final data = await _post('/v1/digests/$digestId/read');
    return Digest.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<Memory>> listMemories() async {
    final data = await _get('/v1/memory');
    return _list(data, Memory.fromJson);
  }

  Future<void> forgetMemory(String memoryId) async {
    final response =
        await _dio.delete<Map<String, dynamic>>('/v1/memory/$memoryId');
    if ((response.statusCode ?? 500) >= 400) _unwrap(response);
  }

  // -- Workspaces (Phase 4) -----------------------------------------------

  Future<List<Workspace>> listWorkspaces({bool includeArchived = false}) async {
    final data = await _get('/v1/workspaces', query: {
      if (includeArchived) 'include_archived': true,
    });
    return _list(data, Workspace.fromJson);
  }

  Future<Workspace> createWorkspace({
    required String name,
    String? description,
    String? color,
  }) async {
    final data = await _post('/v1/workspaces', body: {
      'name': name,
      if (description != null && description.isNotEmpty)
        'description': description,
      if (color != null) 'color': color,
    });
    return Workspace.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Workspace> updateWorkspace(
    String workspaceId, {
    String? name,
    String? description,
    bool? archived,
  }) async {
    final data = await _patch('/v1/workspaces/$workspaceId', body: {
      if (name != null) 'name': name,
      if (description != null) 'description': description,
      if (archived != null) 'archived': archived,
    });
    return Workspace.fromJson(data['data'] as Map<String, dynamic>);
  }

  /// Archives rather than destroys: the notes inside become private to their
  /// authors again. Nothing is lost.
  Future<void> deleteWorkspace(String workspaceId) =>
      _delete('/v1/workspaces/$workspaceId');

  Future<List<Member>> workspaceMembers(String workspaceId) async {
    final data = await _get('/v1/workspaces/$workspaceId/members');
    return _list(data, Member.fromJson);
  }

  Future<Member> addWorkspaceMember(
    String workspaceId, {
    required String userId,
    WorkspaceRole role = WorkspaceRole.editor,
  }) async {
    final data = await _post('/v1/workspaces/$workspaceId/members',
        body: {'user_id': userId, 'role': role.param});
    return Member.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> removeWorkspaceMember(String workspaceId, String userId) =>
      _delete('/v1/workspaces/$workspaceId/members/$userId');

  Future<List<Member>> accountMembers() async {
    final data = await _get('/v1/members');
    return _list(data, Member.fromJson);
  }

  Future<Member> setMemberRole(String userId, AccountRole role) async {
    final data =
        await _patch('/v1/members/$userId/role', body: {'role': role.param});
    return Member.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> removeMember(String userId) => _delete('/v1/members/$userId');

  Future<List<Invitation>> listInvitations() async {
    final data = await _get('/v1/invitations');
    return _list(data, Invitation.fromJson);
  }

  Future<Invitation> invite({
    required String email,
    AccountRole role = AccountRole.member,
    String? workspaceId,
  }) async {
    final data = await _post('/v1/invitations', body: {
      'email': email,
      'role': role.param,
      if (workspaceId != null) 'workspace_id': workspaceId,
    });
    return Invitation.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> revokeInvitation(String invitationId) =>
      _delete('/v1/invitations/$invitationId');

  Future<void> acceptInvitation(String token) async {
    await _post('/v1/invitations/accept', body: {'token': token});
  }

  // -- Comments and mentions ----------------------------------------------

  Future<List<Comment>> listComments(String entryId) async {
    final data = await _get('/v1/entries/$entryId/comments');
    return _list(data, Comment.fromJson);
  }

  Future<Comment> postComment(String entryId, String body,
      {String? parentId}) async {
    final data = await _post('/v1/entries/$entryId/comments', body: {
      'body': body,
      if (parentId != null) 'parent_id': parentId,
    });
    return Comment.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Comment> editComment(String commentId, String body) async {
    final data = await _patch('/v1/comments/$commentId', body: {'body': body});
    return Comment.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> deleteComment(String commentId) =>
      _delete('/v1/comments/$commentId');

  Future<void> resolveComment(String commentId) async {
    await _post('/v1/comments/$commentId/resolve');
  }

  Future<List<Mention>> listMentions({bool unreadOnly = false}) async {
    final data = await _get('/v1/mentions',
        query: {if (unreadOnly) 'unread_only': true});
    return _list(data, Mention.fromJson);
  }

  Future<void> markMentionRead(String mentionId) async {
    await _post('/v1/mentions/$mentionId/read');
  }

  // -- Sharing -------------------------------------------------------------

  /// The response is the only place the plaintext token exists. Nothing on the
  /// server can produce it again, so a caller that discards it has lost it.
  Future<ShareLink> shareEntry(
    String entryId, {
    DateTime? expiresAt,
    bool allowComments = false,
  }) async {
    final data = await _post('/v1/entries/$entryId/share', body: {
      if (expiresAt != null) 'expires_at': expiresAt.toUtc().toIso8601String(),
      'allow_comments': allowComments,
    });
    return ShareLink.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<ShareLink>> listShares() async {
    final data = await _get('/v1/shares');
    return _list(data, ShareLink.fromJson);
  }

  Future<void> revokeShare(String linkId) => _delete('/v1/shares/$linkId');

  // -- Integrations --------------------------------------------------------

  Future<List<Connection>> listIntegrations() async {
    final data = await _get('/v1/integrations');
    return _list(data, Connection.fromJson);
  }

  Future<Connection> connectIntegration({
    required SyncProvider provider,
    required String accessToken,
    String? refreshToken,
    String? label,
    SyncDirection direction = SyncDirection.pull,
  }) async {
    final data = await _post('/v1/integrations', body: {
      'provider': provider.param,
      'access_token': accessToken,
      if (refreshToken != null) 'refresh_token': refreshToken,
      if (label != null) 'label': label,
      'direction': direction.param,
    });
    return Connection.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> disconnectIntegration(String connectionId) =>
      _delete('/v1/integrations/$connectionId');

  Future<SyncReport> syncNow(String connectionId) async {
    final data = await _post('/v1/integrations/$connectionId/sync');
    return SyncReport.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<SyncConflict>> listConflicts() async {
    final data = await _get('/v1/integrations/conflicts');
    return _list(data, SyncConflict.fromJson);
  }

  Future<void> resolveConflict(String linkId, {required String keep}) async {
    await _post('/v1/integrations/conflicts/$linkId/resolve',
        body: {'keep': keep});
  }

  // -- Administration ------------------------------------------------------

  Future<AccountOverview> adminOverview() async {
    final data = await _get('/v1/admin/overview');
    return AccountOverview.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<AuditEntry>> auditLog({String? action, int limit = 100}) async {
    final data = await _get('/v1/admin/audit', query: {
      if (action != null && action.isNotEmpty) 'action': action,
      'limit': limit,
    });
    return _list(data, AuditEntry.fromJson);
  }

  Future<List<UsagePoint>> adminUsage({int days = 30}) async {
    final data = await _get('/v1/admin/usage', query: {'days': days});
    return _list(data, UsagePoint.fromJson);
  }

  Future<OperationalHealth> adminHealth() async {
    final data = await _get('/v1/admin/health');
    return OperationalHealth.fromJson(data['data'] as Map<String, dynamic>);
  }

  /// Collections always arrive wrapped in `data` (API.md §3.2).
  List<T> _list<T>(
          Map<String, dynamic> data, T Function(Map<String, dynamic>) parse) =>
      ((data['data'] as List<dynamic>?) ?? const [])
          .map((item) => parse(item as Map<String, dynamic>))
          .toList(growable: false);

  static String _day(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';
}

final apiProvider = Provider<MindflowApi>((ref) {
  throw UnimplementedError('apiProvider must be overridden at app start');
});

/// One event from the streaming assistant endpoint.
///
/// A sealed pair rather than a nullable field: "a fragment arrived" and "the
/// answer is finished" are different things, and a single class with both
/// optional would let a caller read the wrong one without the compiler
/// objecting.
sealed class AssistantEvent {
  const AssistantEvent();

  factory AssistantEvent.delta(String text) = AssistantDelta;
  factory AssistantEvent.done(Answer answer) = AssistantDone;
}

class AssistantDelta extends AssistantEvent {
  const AssistantDelta(this.text);
  final String text;
}

class AssistantDone extends AssistantEvent {
  const AssistantDone(this.answer);
  final Answer answer;
}
