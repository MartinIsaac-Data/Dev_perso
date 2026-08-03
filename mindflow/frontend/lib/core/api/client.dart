/// HTTP client for the MindFlow API.
library;

import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
