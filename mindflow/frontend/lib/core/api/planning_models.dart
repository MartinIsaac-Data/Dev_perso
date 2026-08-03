/// DTOs for the phase-2 surface: agenda, subtasks, reminders, notifications,
/// search, statistics, history and the library.
///
/// Same tolerance rule as `models.dart`: an unknown enum value maps to a neutral
/// fallback rather than throwing (API.md §12.2). A client that crashes on a
/// value the server added turns an additive change into an outage.
library;

import 'models.dart';

/// A defensively-typed nested object.
///
/// `jsonDecode` yields `Map<String, dynamic>`, but a literal written by hand —
/// in a test, a fixture, a default — is `Map<dynamic, dynamic>`, and a bare cast
/// throws on it. Copying costs nothing at these sizes and removes a whole class
/// of "works against the server, fails against the fixture" bugs.
Map<String, dynamic> asMap(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

// --------------------------------------------------------------------------- //
// Subtasks
// --------------------------------------------------------------------------- //
class Subtask {
  const Subtask({
    required this.id,
    required this.entryId,
    required this.title,
    required this.position,
    this.completedAt,
  });

  final String id;
  final String entryId;
  final String title;
  final int position;
  final DateTime? completedAt;

  bool get done => completedAt != null;

  Subtask copyWith(
          {String? title,
          DateTime? completedAt,
          bool clearCompleted = false}) =>
      Subtask(
        id: id,
        entryId: entryId,
        title: title ?? this.title,
        position: position,
        completedAt: clearCompleted ? null : (completedAt ?? this.completedAt),
      );

  factory Subtask.fromJson(Map<String, dynamic> json) => Subtask(
        id: json['id'] as String,
        entryId: json['entry_id'] as String,
        title: (json['title'] as String?) ?? '',
        position: (json['position'] as num?)?.toInt() ?? 0,
        completedAt: parseDate(json['completed_at']),
      );
}

class SubtaskProgress {
  const SubtaskProgress({this.done = 0, this.total = 0});

  final int done;
  final int total;

  bool get any => total > 0;
  bool get complete => total > 0 && done == total;
  double get ratio => total == 0 ? 0 : done / total;

  factory SubtaskProgress.fromJson(Map<String, dynamic> json) =>
      SubtaskProgress(
        done: (json['done'] as num?)?.toInt() ?? 0,
        total: (json['total'] as num?)?.toInt() ?? 0,
      );
}

// --------------------------------------------------------------------------- //
// Agenda and calendar
// --------------------------------------------------------------------------- //
enum AgendaView {
  day,
  week,
  month;

  String get param => name;

  String get label => switch (this) {
        AgendaView.day => 'Jour',
        AgendaView.week => 'Semaine',
        AgendaView.month => 'Mois',
      };
}

class AgendaItem {
  const AgendaItem({required this.entry, required this.day, this.subtasks});

  final Entry entry;
  final DateTime day;
  final SubtaskProgress? subtasks;

  factory AgendaItem.fromJson(Map<String, dynamic> json) => AgendaItem(
        entry: Entry.fromJson(asMap(json['entry'])),
        day: parseDate(json['day']) ?? DateTime.now(),
        subtasks: json['subtasks'] == null
            ? null
            : SubtaskProgress.fromJson(asMap(json['subtasks'])),
      );
}

class AgendaDay {
  const AgendaDay({required this.day, required this.items});

  final DateTime day;
  final List<AgendaItem> items;

  bool get isEmpty => items.isEmpty;

  factory AgendaDay.fromJson(Map<String, dynamic> json) => AgendaDay(
        day: parseDate(json['day']) ?? DateTime.now(),
        items: ((json['items'] as List<dynamic>?) ?? const [])
            .map((item) => AgendaItem.fromJson(asMap(item)))
            .toList(growable: false),
      );
}

class Agenda {
  const Agenda({
    required this.view,
    required this.start,
    required this.end,
    required this.days,
    this.overdue = const [],
    this.unscheduled = const [],
  });

  final String view;
  final DateTime start;
  final DateTime end;
  final List<AgendaDay> days;

  /// Its own bucket, not pinned to the day it was due: at the bottom of a
  /// scrolled-away day, an overdue task is one nobody sees again.
  final List<AgendaItem> overdue;
  final List<AgendaItem> unscheduled;

  int get total => days.fold(0, (sum, day) => sum + day.items.length);

  factory Agenda.fromJson(Map<String, dynamic> json) => Agenda(
        view: (json['view'] as String?) ?? 'week',
        start: parseDate(json['start']) ?? DateTime.now(),
        end: parseDate(json['end']) ?? DateTime.now(),
        days: ((json['days'] as List<dynamic>?) ?? const [])
            .map((day) => AgendaDay.fromJson(asMap(day)))
            .toList(growable: false),
        overdue: ((json['overdue'] as List<dynamic>?) ?? const [])
            .map((item) => AgendaItem.fromJson(asMap(item)))
            .toList(growable: false),
        unscheduled: ((json['unscheduled'] as List<dynamic>?) ?? const [])
            .map((item) => AgendaItem.fromJson(asMap(item)))
            .toList(growable: false),
      );
}

class CalendarCell {
  const CalendarCell({
    required this.day,
    required this.total,
    required this.done,
    required this.pending,
    required this.overdue,
    required this.captures,
  });

  final DateTime day;
  final int total;
  final int done;
  final int pending;
  final int overdue;
  final int captures;

  bool get isEmpty => total == 0 && captures == 0;

  factory CalendarCell.fromJson(Map<String, dynamic> json) => CalendarCell(
        day: parseDate(json['day']) ?? DateTime.now(),
        total: (json['total'] as num?)?.toInt() ?? 0,
        done: (json['done'] as num?)?.toInt() ?? 0,
        pending: (json['pending'] as num?)?.toInt() ?? 0,
        overdue: (json['overdue'] as num?)?.toInt() ?? 0,
        captures: (json['captures'] as num?)?.toInt() ?? 0,
      );
}

class CalendarMonth {
  const CalendarMonth(
      {required this.start, required this.end, required this.cells});

  final DateTime start;
  final DateTime end;
  final List<CalendarCell> cells;

  factory CalendarMonth.fromJson(Map<String, dynamic> json) => CalendarMonth(
        start: parseDate(json['start']) ?? DateTime.now(),
        end: parseDate(json['end']) ?? DateTime.now(),
        cells: ((json['cells'] as List<dynamic>?) ?? const [])
            .map((cell) => CalendarCell.fromJson(asMap(cell)))
            .toList(growable: false),
      );
}

// --------------------------------------------------------------------------- //
// Reminders and notifications
// --------------------------------------------------------------------------- //
enum ReminderStatus { scheduled, sent, failed, cancelled, dismissed, unknown }

ReminderStatus reminderStatusFrom(String? raw) => switch (raw) {
      'scheduled' => ReminderStatus.scheduled,
      'sent' => ReminderStatus.sent,
      'failed' => ReminderStatus.failed,
      'cancelled' => ReminderStatus.cancelled,
      'dismissed' => ReminderStatus.dismissed,
      _ => ReminderStatus.unknown,
    };

class Reminder {
  const Reminder({
    required this.id,
    required this.remindAt,
    required this.status,
    this.entryId,
    this.channel = 'push',
    this.offsetRule,
    this.title,
    this.body,
  });

  final String id;
  final String? entryId;
  final DateTime remindAt;
  final ReminderStatus status;
  final String channel;

  /// The wording that generated it ("-15m"), so the interface can show the rule
  /// rather than a bare timestamp.
  final String? offsetRule;
  final String? title;
  final String? body;

  bool get isPending => status == ReminderStatus.scheduled;
  bool get isAutomatic => offsetRule != null;

  factory Reminder.fromJson(Map<String, dynamic> json) => Reminder(
        id: json['id'] as String,
        entryId: json['entry_id'] as String?,
        remindAt: parseDate(json['remind_at']) ?? DateTime.now(),
        status: reminderStatusFrom(json['status'] as String?),
        channel: (json['channel'] as String?) ?? 'push',
        offsetRule: json['offset_rule'] as String?,
        title: json['title'] as String?,
        body: json['body'] as String?,
      );
}

enum NotificationKind {
  reminder,
  dueSoon,
  overdue,
  captureReady,
  captureFailed,
  reviewPending,
  digest,
  system,
  unknown,
}

NotificationKind notificationKindFrom(String? raw) => switch (raw) {
      'reminder' => NotificationKind.reminder,
      'due_soon' => NotificationKind.dueSoon,
      'overdue' => NotificationKind.overdue,
      'capture_ready' => NotificationKind.captureReady,
      'capture_failed' => NotificationKind.captureFailed,
      'review_pending' => NotificationKind.reviewPending,
      'digest' => NotificationKind.digest,
      'system' => NotificationKind.system,
      _ => NotificationKind.unknown,
    };

class AppNotification {
  const AppNotification({
    required this.id,
    required this.kind,
    required this.title,
    required this.createdAt,
    this.body,
    this.entryId,
    this.captureId,
    this.readAt,
  });

  final String id;
  final NotificationKind kind;
  final String title;
  final String? body;
  final String? entryId;
  final String? captureId;
  final DateTime? readAt;
  final DateTime createdAt;

  bool get unread => readAt == null;

  factory AppNotification.fromJson(Map<String, dynamic> json) =>
      AppNotification(
        id: json['id'] as String,
        kind: notificationKindFrom(json['kind'] as String?),
        title: (json['title'] as String?) ?? '',
        body: json['body'] as String?,
        entryId: json['entry_id'] as String?,
        captureId: json['capture_id'] as String?,
        readAt: parseDate(json['read_at']),
        createdAt: parseDate(json['created_at']) ?? DateTime.now(),
      );
}

class NotificationCentre {
  const NotificationCentre({this.unread = 0, this.items = const []});

  final int unread;
  final List<AppNotification> items;

  factory NotificationCentre.fromJson(Map<String, dynamic> json) =>
      NotificationCentre(
        unread: (json['unread'] as num?)?.toInt() ?? 0,
        items: ((json['items'] as List<dynamic>?) ?? const [])
            .map((item) => AppNotification.fromJson(asMap(item)))
            .toList(growable: false),
      );
}

// --------------------------------------------------------------------------- //
// Search
// --------------------------------------------------------------------------- //
class ParsedQuery {
  const ParsedQuery({
    this.text = '',
    this.types = const [],
    this.statuses = const [],
    this.priorities = const [],
    this.tags = const [],
    this.projects = const [],
    this.overdue = false,
    this.recurring = false,
    this.pinned = false,
    this.ignored = const [],
  });

  final String text;
  final List<String> types;
  final List<String> statuses;
  final List<String> priorities;
  final List<String> tags;
  final List<String> projects;
  final bool overdue;
  final bool recurring;
  final bool pinned;

  /// Tokens the server could not map. Shown as "ignoré" chips rather than
  /// silently dropped — a search box that quietly returns everything teaches the
  /// user nothing.
  final List<String> ignored;

  bool get hasFilters =>
      types.isNotEmpty ||
      statuses.isNotEmpty ||
      priorities.isNotEmpty ||
      tags.isNotEmpty ||
      projects.isNotEmpty ||
      overdue ||
      recurring ||
      pinned;

  static List<String> _strings(dynamic value) =>
      ((value as List<dynamic>?) ?? const [])
          .map((item) => item.toString())
          .toList();

  factory ParsedQuery.fromJson(Map<String, dynamic> json) => ParsedQuery(
        text: (json['text'] as String?) ?? '',
        types: _strings(json['types']),
        statuses: _strings(json['statuses']),
        priorities: _strings(json['priorities']),
        tags: _strings(json['tags']),
        projects: _strings(json['projects']),
        overdue: json['overdue'] as bool? ?? false,
        recurring: json['recurring'] as bool? ?? false,
        pinned: json['pinned'] as bool? ?? false,
        ignored: _strings(json['ignored']),
      );
}

class SearchHit {
  const SearchHit({required this.entry, this.rank = 0, this.snippet});

  final Entry entry;
  final double rank;

  /// Server-rendered highlight, delimited by « ». Rendered rather than
  /// re-tokenised on the client, which would disagree with the ranking about
  /// what actually matched.
  final String? snippet;

  factory SearchHit.fromJson(Map<String, dynamic> json) => SearchHit(
        entry: Entry.fromJson(asMap(json['entry'])),
        rank: (json['rank'] as num?)?.toDouble() ?? 0,
        snippet: json['snippet'] as String?,
      );
}

class SearchResults {
  const SearchResults({
    required this.query,
    required this.hits,
    this.total = 0,
    this.tookMs = 0,
  });

  final ParsedQuery query;
  final List<SearchHit> hits;
  final int total;
  final int tookMs;

  bool get isEmpty => hits.isEmpty;

  factory SearchResults.fromJson(Map<String, dynamic> json) => SearchResults(
        query: ParsedQuery.fromJson(asMap(json['query'])),
        hits: ((json['hits'] as List<dynamic>?) ?? const [])
            .map((hit) => SearchHit.fromJson(asMap(hit)))
            .toList(growable: false),
        total: (json['total'] as num?)?.toInt() ?? 0,
        tookMs: (json['took_ms'] as num?)?.toInt() ?? 0,
      );
}

class QuickHit {
  const QuickHit({
    required this.kind,
    required this.id,
    required this.title,
    this.subtitle,
    this.icon,
  });

  final String kind;
  final String id;
  final String title;
  final String? subtitle;
  final String? icon;

  factory QuickHit.fromJson(Map<String, dynamic> json) => QuickHit(
        kind: (json['kind'] as String?) ?? 'entry',
        id: (json['id'] as String?) ?? '',
        title: (json['title'] as String?) ?? '',
        subtitle: json['subtitle'] as String?,
        icon: json['icon'] as String?,
      );
}

class QuickResults {
  const QuickResults({
    this.entries = const [],
    this.projects = const [],
    this.tags = const [],
    this.captures = const [],
  });

  final List<QuickHit> entries;
  final List<QuickHit> projects;
  final List<QuickHit> tags;
  final List<QuickHit> captures;

  bool get isEmpty =>
      entries.isEmpty && projects.isEmpty && tags.isEmpty && captures.isEmpty;

  static List<QuickHit> _hits(dynamic value) =>
      ((value as List<dynamic>?) ?? const [])
          .map((hit) => QuickHit.fromJson(asMap(hit)))
          .toList(growable: false);

  factory QuickResults.fromJson(Map<String, dynamic> json) => QuickResults(
        entries: _hits(json['entries']),
        projects: _hits(json['projects']),
        tags: _hits(json['tags']),
        captures: _hits(json['captures']),
      );
}

// --------------------------------------------------------------------------- //
// Statistics
// --------------------------------------------------------------------------- //
class DailyPoint {
  const DailyPoint({
    required this.day,
    this.created = 0,
    this.completed = 0,
    this.captured = 0,
  });

  final DateTime day;
  final int created;
  final int completed;
  final int captured;

  int get max => [created, completed, captured].reduce((a, b) => a > b ? a : b);

  factory DailyPoint.fromJson(Map<String, dynamic> json) => DailyPoint(
        day: parseDate(json['day']) ?? DateTime.now(),
        created: (json['created'] as num?)?.toInt() ?? 0,
        completed: (json['completed'] as num?)?.toInt() ?? 0,
        captured: (json['captured'] as num?)?.toInt() ?? 0,
      );
}

class Breakdown {
  const Breakdown({
    required this.key,
    required this.label,
    required this.total,
    this.done = 0,
    this.completionRate = 0,
    this.color,
  });

  final String key;
  final String label;
  final int total;
  final int done;
  final double completionRate;
  final String? color;

  factory Breakdown.fromJson(Map<String, dynamic> json) => Breakdown(
        key: (json['key'] as String?) ?? '',
        label: (json['label'] as String?) ?? '',
        total: (json['total'] as num?)?.toInt() ?? 0,
        done: (json['done'] as num?)?.toInt() ?? 0,
        completionRate: (json['completion_rate'] as num?)?.toDouble() ?? 0,
        color: json['color'] as String?,
      );
}

class Streak {
  const Streak({this.current = 0, this.longest = 0, this.lastActiveDay});

  final int current;
  final int longest;
  final DateTime? lastActiveDay;

  factory Streak.fromJson(Map<String, dynamic> json) => Streak(
        current: (json['current'] as num?)?.toInt() ?? 0,
        longest: (json['longest'] as num?)?.toInt() ?? 0,
        lastActiveDay: parseDate(json['last_active_day']),
      );
}

class Statistics {
  const Statistics({
    required this.windowDays,
    required this.captures,
    required this.entriesCreated,
    required this.tasksCompleted,
    required this.tasksOpen,
    required this.tasksOverdue,
    required this.completionRate,
    required this.streak,
    this.medianCompletionHours,
    this.byType = const [],
    this.byPriority = const [],
    this.byProject = const [],
    this.topTags = const [],
    this.daily = const [],
    this.corrections = 0,
    this.correctionRate = 0,
    this.capturesWithoutEntries = 0,
    this.needsReview = 0,
    this.aiCostMicroEur = 0,
    this.busiestHour,
  });

  final int windowDays;
  final int captures;
  final int entriesCreated;
  final int tasksCompleted;
  final int tasksOpen;
  final int tasksOverdue;
  final double completionRate;
  final double? medianCompletionHours;
  final Streak streak;
  final List<Breakdown> byType;
  final List<Breakdown> byPriority;
  final List<Breakdown> byProject;
  final List<Breakdown> topTags;
  final List<DailyPoint> daily;

  /// The unflattering half. Rendered as prominently as the rest: a dashboard
  /// that counts only successes teaches nothing.
  final int corrections;
  final double correctionRate;
  final int capturesWithoutEntries;
  final int needsReview;
  final int aiCostMicroEur;
  final int? busiestHour;

  double get aiCostEur => aiCostMicroEur / 1000000;

  static List<Breakdown> _breakdowns(dynamic value) =>
      ((value as List<dynamic>?) ?? const [])
          .map((item) => Breakdown.fromJson(asMap(item)))
          .toList(growable: false);

  factory Statistics.fromJson(Map<String, dynamic> json) => Statistics(
        windowDays: (json['window_days'] as num?)?.toInt() ?? 30,
        captures: (json['captures'] as num?)?.toInt() ?? 0,
        entriesCreated: (json['entries_created'] as num?)?.toInt() ?? 0,
        tasksCompleted: (json['tasks_completed'] as num?)?.toInt() ?? 0,
        tasksOpen: (json['tasks_open'] as num?)?.toInt() ?? 0,
        tasksOverdue: (json['tasks_overdue'] as num?)?.toInt() ?? 0,
        completionRate: (json['completion_rate'] as num?)?.toDouble() ?? 0,
        medianCompletionHours:
            (json['median_completion_hours'] as num?)?.toDouble(),
        streak: Streak.fromJson(asMap(json['streak'])),
        byType: _breakdowns(json['by_type']),
        byPriority: _breakdowns(json['by_priority']),
        byProject: _breakdowns(json['by_project']),
        topTags: _breakdowns(json['top_tags']),
        daily: ((json['daily'] as List<dynamic>?) ?? const [])
            .map((point) => DailyPoint.fromJson(asMap(point)))
            .toList(growable: false),
        corrections: (json['corrections'] as num?)?.toInt() ?? 0,
        correctionRate: (json['correction_rate'] as num?)?.toDouble() ?? 0,
        capturesWithoutEntries:
            (json['captures_without_entries'] as num?)?.toInt() ?? 0,
        needsReview: (json['needs_review'] as num?)?.toInt() ?? 0,
        aiCostMicroEur: (json['ai_cost_micro_eur'] as num?)?.toInt() ?? 0,
        busiestHour: (json['busiest_hour'] as num?)?.toInt(),
      );
}

// --------------------------------------------------------------------------- //
// History / Timeline
// --------------------------------------------------------------------------- //
class ActivityEvent {
  const ActivityEvent({
    required this.id,
    required this.action,
    required this.occurredAt,
    this.entryId,
    this.captureId,
    this.projectId,
    this.subjectLabel,
    this.actorType = 'user',
    this.detail = const {},
  });

  final int id;
  final String action;
  final String? entryId;
  final String? captureId;
  final String? projectId;

  /// Denormalised server-side, so the timeline survives the deletion of its own
  /// subject. A history that goes blank is not a history.
  final String? subjectLabel;
  final String actorType;
  final Map<String, dynamic> detail;
  final DateTime occurredAt;

  bool get bySystem => actorType != 'user';

  factory ActivityEvent.fromJson(Map<String, dynamic> json) => ActivityEvent(
        id: (json['id'] as num?)?.toInt() ?? 0,
        action: (json['action'] as String?) ?? 'edited',
        entryId: json['entry_id'] as String?,
        captureId: json['capture_id'] as String?,
        projectId: json['project_id'] as String?,
        subjectLabel: json['subject_label'] as String?,
        actorType: (json['actor_type'] as String?) ?? 'user',
        detail: asMap(json['detail']),
        occurredAt: parseDate(json['occurred_at']) ?? DateTime.now(),
      );
}

// --------------------------------------------------------------------------- //
// Library
// --------------------------------------------------------------------------- //
class Tag {
  const Tag({
    required this.id,
    required this.label,
    required this.normalized,
    this.usageCount = 0,
    this.color,
    this.pinned = false,
  });

  final String id;
  final String label;
  final String normalized;
  final int usageCount;
  final String? color;
  final bool pinned;

  factory Tag.fromJson(Map<String, dynamic> json) => Tag(
        id: json['id'] as String,
        label: (json['label'] as String?) ?? '',
        normalized: (json['normalized'] as String?) ?? '',
        usageCount: (json['usage_count'] as num?)?.toInt() ?? 0,
        color: json['color'] as String?,
        pinned: json['pinned'] as bool? ?? false,
      );
}

class SavedFilter {
  const SavedFilter({
    required this.id,
    required this.name,
    required this.query,
    this.icon,
    this.color,
    this.position = 0,
    this.pinned = false,
  });

  final String id;
  final String name;

  /// The query *string*, not a compiled predicate: the grammar is the contract,
  /// so a filter saved today keeps working when the parser gains a keyword.
  final String query;
  final String? icon;
  final String? color;
  final int position;
  final bool pinned;

  factory SavedFilter.fromJson(Map<String, dynamic> json) => SavedFilter(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? '',
        query: (json['query'] as String?) ?? '',
        icon: json['icon'] as String?,
        color: json['color'] as String?,
        position: (json['position'] as num?)?.toInt() ?? 0,
        pinned: json['pinned'] as bool? ?? false,
      );
}

class ProjectDetail {
  const ProjectDetail({
    required this.id,
    required this.name,
    required this.slug,
    this.description,
    this.color,
    this.icon,
    this.aliases = const [],
    this.pinned = false,
    this.archived = false,
    this.openCount = 0,
    this.totalCount = 0,
  });

  final String id;
  final String name;
  final String slug;
  final String? description;
  final String? color;
  final String? icon;
  final List<String> aliases;
  final bool pinned;
  final bool archived;
  final int openCount;
  final int totalCount;

  int get doneCount => (totalCount - openCount).clamp(0, totalCount);
  double get progress => totalCount == 0 ? 0 : doneCount / totalCount;

  factory ProjectDetail.fromJson(Map<String, dynamic> json) => ProjectDetail(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? '',
        slug: (json['slug'] as String?) ?? '',
        description: json['description'] as String?,
        color: json['color'] as String?,
        icon: json['icon'] as String?,
        aliases:
            ((json['aliases'] as List<dynamic>?) ?? const []).cast<String>(),
        pinned: json['pinned'] as bool? ?? false,
        archived: json['archived'] as bool? ?? false,
        openCount: (json['open_count'] as num?)?.toInt() ?? 0,
        totalCount: (json['total_count'] as num?)?.toInt() ?? 0,
      );
}

class RegisteredDevice {
  const RegisteredDevice({
    required this.id,
    required this.installId,
    required this.platform,
    required this.pushProvider,
    this.name,
    this.pushEnabled = false,
    this.lastSeenAt,
  });

  final String id;
  final String installId;
  final String platform;
  final String pushProvider;
  final String? name;
  final bool pushEnabled;
  final DateTime? lastSeenAt;

  factory RegisteredDevice.fromJson(Map<String, dynamic> json) =>
      RegisteredDevice(
        id: json['id'] as String,
        installId: (json['install_id'] as String?) ?? '',
        platform: (json['platform'] as String?) ?? 'unknown',
        pushProvider: (json['push_provider'] as String?) ?? 'none',
        name: json['name'] as String?,
        pushEnabled: json['push_enabled'] as bool? ?? false,
        lastSeenAt: parseDate(json['last_seen_at']),
      );
}
