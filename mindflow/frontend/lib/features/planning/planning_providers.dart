/// Read models and mutations for the phase-2 screens.
///
/// Two performance decisions run through this file, both of which matter more
/// than they look:
///
/// * **`select` over `watch`.** A screen that watches a whole controller
///   rebuilds on every field change; one that selects the field it renders
///   rebuilds when that field changes. On the agenda, where a keystroke in the
///   search box would otherwise rebuild sixty rows, this is the difference
///   between smooth and not.
/// * **Families keyed by value objects.** `agendaProvider(AgendaQuery(...))`
///   caches per window, so moving to next week and back is instant instead of a
///   round trip. The key implements `==`, without which every rebuild would
///   create a new provider and defeat the cache entirely.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/client.dart';
import '../../core/api/models.dart';
import '../../core/api/planning_models.dart';

// --------------------------------------------------------------------------- //
// Agenda and calendar
// --------------------------------------------------------------------------- //

/// The identity of an agenda request.
///
/// A value object with `==` and `hashCode`, which is what makes the family
/// cache work: without them Riverpod would treat every rebuild's query as a new
/// provider and refetch on each frame.
class AgendaQuery {
  const AgendaQuery({
    this.view = AgendaView.week,
    this.anchor,
    this.includeDone = true,
    this.includeUnscheduled = false,
    this.projectId,
  });

  final AgendaView view;
  final DateTime? anchor;
  final bool includeDone;
  final bool includeUnscheduled;
  final String? projectId;

  /// Normalised to the day: two anchors within the same day describe the same
  /// window, and treating them as different keys would halve the cache hit rate
  /// for no benefit.
  DateTime? get _anchorDay => anchor == null
      ? null
      : DateTime(anchor!.year, anchor!.month, anchor!.day);

  AgendaQuery copyWith({
    AgendaView? view,
    DateTime? anchor,
    bool? includeDone,
    bool? includeUnscheduled,
    String? projectId,
    bool clearProject = false,
  }) =>
      AgendaQuery(
        view: view ?? this.view,
        anchor: anchor ?? this.anchor,
        includeDone: includeDone ?? this.includeDone,
        includeUnscheduled: includeUnscheduled ?? this.includeUnscheduled,
        projectId: clearProject ? null : (projectId ?? this.projectId),
      );

  @override
  bool operator ==(Object other) =>
      other is AgendaQuery &&
      other.view == view &&
      other._anchorDay == _anchorDay &&
      other.includeDone == includeDone &&
      other.includeUnscheduled == includeUnscheduled &&
      other.projectId == projectId;

  @override
  int get hashCode =>
      Object.hash(view, _anchorDay, includeDone, includeUnscheduled, projectId);
}

final agendaQueryProvider =
    StateProvider<AgendaQuery>((ref) => const AgendaQuery());

final agendaProvider =
    FutureProvider.autoDispose.family<Agenda, AgendaQuery>((ref, query) async {
  // Kept briefly after the last listener drops so paging back and forth through
  // weeks does not refetch each time.
  ref.keepAlive();
  return ref.watch(apiProvider).agenda(
        view: query.view,
        anchor: query.anchor,
        includeDone: query.includeDone,
        includeUnscheduled: query.includeUnscheduled,
        projectId: query.projectId,
      );
});

final calendarMonthProvider = StateProvider<DateTime>((ref) {
  final now = DateTime.now();
  return DateTime(now.year, now.month);
});

final calendarProvider = FutureProvider.autoDispose
    .family<CalendarMonth, DateTime>((ref, month) async {
  ref.keepAlive();
  return ref.watch(apiProvider).calendar(month: month);
});

// --------------------------------------------------------------------------- //
// Subtasks
// --------------------------------------------------------------------------- //
final subtasksProvider = FutureProvider.autoDispose
    .family<List<Subtask>, String>((ref, entryId) async {
  return ref.watch(apiProvider).listSubtasks(entryId);
});

// --------------------------------------------------------------------------- //
// Reminders and notifications
// --------------------------------------------------------------------------- //
final remindersProvider = FutureProvider.autoDispose
    .family<List<Reminder>, String?>((ref, entryId) async {
  return ref.watch(apiProvider).listReminders(entryId: entryId);
});

final notificationsProvider =
    FutureProvider.autoDispose<NotificationCentre>((ref) async {
  return ref.watch(apiProvider).notifications();
});

/// Just the badge count. A separate provider so the shell's unread dot does not
/// rebuild every screen that happens to watch the notification list.
final unreadCountProvider = Provider.autoDispose<int>((ref) {
  return ref.watch(notificationsProvider).maybeWhen(
        data: (centre) => centre.unread,
        orElse: () => 0,
      );
});

// --------------------------------------------------------------------------- //
// Search
// --------------------------------------------------------------------------- //
final searchQueryProvider = StateProvider<String>((ref) => '');

final searchResultsProvider =
    FutureProvider.autoDispose<SearchResults?>((ref) async {
  final query = ref.watch(searchQueryProvider).trim();
  if (query.isEmpty) return null;
  return ref.watch(apiProvider).search(query);
});

final quickSearchProvider =
    FutureProvider.autoDispose.family<QuickResults, String>((ref, query) async {
  if (query.trim().length < 2) return const QuickResults();
  return ref.watch(apiProvider).quickSearch(query);
});

// --------------------------------------------------------------------------- //
// Statistics and history
// --------------------------------------------------------------------------- //
final statsWindowProvider = StateProvider<int>((ref) => 30);

final statisticsProvider = FutureProvider.autoDispose<Statistics>((ref) async {
  return ref
      .watch(apiProvider)
      .statistics(windowDays: ref.watch(statsWindowProvider));
});

final activityProvider = FutureProvider.autoDispose
    .family<List<ActivityEvent>, String?>((ref, entryId) async {
  return ref.watch(apiProvider).activity(entryId: entryId);
});

// --------------------------------------------------------------------------- //
// Library
// --------------------------------------------------------------------------- //
final tagsProvider = FutureProvider.autoDispose<List<Tag>>((ref) async {
  return ref.watch(apiProvider).listTags();
});

final savedFiltersProvider =
    FutureProvider.autoDispose<List<SavedFilter>>((ref) async {
  return ref.watch(apiProvider).listFilters();
});

final projectsProvider =
    FutureProvider.autoDispose<List<ProjectDetail>>((ref) async {
  return ref.watch(apiProvider).listProjectsDetailed();
});

// --------------------------------------------------------------------------- //
// Mutations
// --------------------------------------------------------------------------- //

/// One place for every write, so no screen has to know how the reads are cached.
///
/// Invalidation is explicit and deliberately broad: correctness first. A stale
/// count on the agenda after completing a task is a bug the user sees; one extra
/// request is not.
class PlanningActions {
  const PlanningActions(this._ref);

  final Ref _ref;

  MindflowApi get _api => _ref.read(apiProvider);

  void _invalidateEverythingCounting() {
    _ref
      ..invalidate(statisticsProvider)
      ..invalidate(notificationsProvider);
    // The agenda and calendar are families: invalidating the family clears every
    // cached window, which is what we want after a change that can move an item
    // between weeks.
    _ref.invalidate(agendaProvider);
    _ref.invalidate(calendarProvider);
  }

  Future<(Entry, Entry?)> completeTask(String entryId) async {
    final result = await _api.completeTask(entryId);
    _invalidateEverythingCounting();
    _ref.invalidate(activityProvider);
    return result;
  }

  Future<Entry> reopenTask(String entryId) async {
    final entry = await _api.reopenTask(entryId);
    _invalidateEverythingCounting();
    return entry;
  }

  Future<Entry> snooze(String entryId, DateTime until) async {
    final entry = await _api.snoozeTask(entryId, until);
    _invalidateEverythingCounting();
    return entry;
  }

  Future<Entry> reschedule(String entryId, DateTime? dueAt) async {
    final entry = await _api.rescheduleTask(entryId, dueAt);
    _invalidateEverythingCounting();
    _ref.invalidate(remindersProvider);
    return entry;
  }

  Future<Entry> setRecurrence(String entryId, String? rule) async {
    final entry = await _api.setRecurrence(entryId, rule);
    _invalidateEverythingCounting();
    return entry;
  }

  Future<Entry> pin(String entryId, {required bool pinned}) async {
    final entry = await _api.pinEntry(entryId, pinned: pinned);
    _invalidateEverythingCounting();
    return entry;
  }

  Future<int> bulkUpdate(
    List<String> ids, {
    String? status,
    String? priority,
    String? projectId,
    bool clearProject = false,
  }) async {
    final matched = await _api.bulkUpdate(
      ids,
      status: status,
      priority: priority,
      projectId: projectId,
      clearProject: clearProject,
    );
    _invalidateEverythingCounting();
    return matched;
  }

  Future<Subtask> addSubtask(String entryId, String title) async {
    final subtask = await _api.addSubtask(entryId, title);
    _ref.invalidate(subtasksProvider(entryId));
    _ref.invalidate(agendaProvider);
    return subtask;
  }

  Future<Subtask> toggleSubtask(Subtask subtask) async {
    final updated =
        await _api.updateSubtask(subtask.id, completed: !subtask.done);
    _ref.invalidate(subtasksProvider(subtask.entryId));
    _ref.invalidate(agendaProvider);
    return updated;
  }

  Future<void> deleteSubtask(Subtask subtask) async {
    await _api.deleteSubtask(subtask.id);
    _ref.invalidate(subtasksProvider(subtask.entryId));
    _ref.invalidate(agendaProvider);
  }

  Future<List<Subtask>> reorderSubtasks(
      String entryId, List<String> orderedIds) async {
    final subtasks = await _api.reorderSubtasks(entryId, orderedIds);
    _ref.invalidate(subtasksProvider(entryId));
    return subtasks;
  }

  Future<Reminder> addReminder(String entryId, DateTime remindAt) async {
    final reminder =
        await _api.createReminder(entryId: entryId, remindAt: remindAt);
    _ref.invalidate(remindersProvider);
    return reminder;
  }

  Future<void> cancelReminder(String reminderId) async {
    await _api.cancelReminder(reminderId);
    _ref.invalidate(remindersProvider);
  }

  Future<void> markNotificationRead(String notificationId) async {
    await _api.markNotificationRead(notificationId);
    _ref.invalidate(notificationsProvider);
  }

  Future<void> markAllNotificationsRead() async {
    await _api.markAllNotificationsRead();
    _ref.invalidate(notificationsProvider);
  }

  Future<List<Tag>> attachTags(String entryId, List<String> labels) async {
    final tags = await _api.attachTags(entryId, labels);
    _ref.invalidate(tagsProvider);
    return tags;
  }

  Future<void> detachTag(String entryId, String tagId) async {
    await _api.detachTag(entryId, tagId);
    _ref.invalidate(tagsProvider);
  }

  Future<Tag> renameTag(String tagId, String label) async {
    final tag = await _api.updateTag(tagId, label: label);
    _ref.invalidate(tagsProvider);
    return tag;
  }

  Future<void> deleteTag(String tagId) async {
    await _api.deleteTag(tagId);
    _ref.invalidate(tagsProvider);
  }

  Future<SavedFilter> saveFilter(
      {required String name, required String query}) async {
    final saved = await _api.createFilter(name: name, query: query);
    _ref.invalidate(savedFiltersProvider);
    return saved;
  }

  Future<void> deleteFilter(String filterId) async {
    await _api.deleteFilter(filterId);
    _ref.invalidate(savedFiltersProvider);
  }

  Future<ProjectDetail> updateProject(
    String projectId, {
    String? name,
    String? description,
    bool? pinned,
    bool? archived,
  }) async {
    final project = await _api.updateProject(
      projectId,
      name: name,
      description: description,
      pinned: pinned,
      archived: archived,
    );
    _ref.invalidate(projectsProvider);
    return project;
  }
}

final planningActionsProvider = Provider<PlanningActions>(PlanningActions.new);
