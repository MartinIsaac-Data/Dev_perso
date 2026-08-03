import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/models.dart';
import 'package:mindflow/core/api/planning_models.dart';

void main() {
  group('Subtask', () {
    test('reads the payload', () {
      final subtask = Subtask.fromJson({
        'id': 's1',
        'entry_id': 'e1',
        'title': 'Préparer les chiffres',
        'position': 100,
        'completed_at': '2026-06-10T08:00:00Z',
      });
      expect(subtask.done, isTrue);
      expect(subtask.position, 100);
    });

    test('an unchecked subtask has no completion instant', () {
      final subtask = Subtask.fromJson({
        'id': 's1',
        'entry_id': 'e1',
        'title': 'À faire',
        'position': 100,
      });
      expect(subtask.done, isFalse);
    });
  });

  group('SubtaskProgress', () {
    test('is complete only when every item is checked', () {
      expect(const SubtaskProgress(done: 3, total: 3).complete, isTrue);
      expect(const SubtaskProgress(done: 2, total: 3).complete, isFalse);
    });

    test('an empty checklist is not complete', () {
      // "0/0 done" would render a full progress bar on a task with no
      // checklist — a lie about work that does not exist.
      expect(const SubtaskProgress().complete, isFalse);
      expect(const SubtaskProgress().any, isFalse);
      expect(const SubtaskProgress().ratio, 0);
    });
  });

  group('Agenda', () {
    test('parses days, overdue and unscheduled buckets separately', () {
      final agenda = Agenda.fromJson({
        'view': 'week',
        'start': '2026-06-08',
        'end': '2026-06-15',
        'days': [
          {
            'day': '2026-06-08',
            'items': [
              {
                'entry': {'id': 'e1', 'entry_type': 'task', 'title': 'A'},
                'day': '2026-06-08',
                'subtasks': {'done': 1, 'total': 2},
              },
            ],
          },
        ],
        'overdue': [
          {
            'entry': {'id': 'e2', 'entry_type': 'task', 'title': 'Vieille'},
            'day': '2026-05-30',
          },
        ],
        'unscheduled': [],
      });

      expect(agenda.days, hasLength(1));
      expect(agenda.total, 1);
      expect(agenda.overdue, hasLength(1));
      expect(agenda.days.first.items.first.subtasks?.done, 1);
    });

    test('tolerates an absent bucket', () {
      final agenda = Agenda.fromJson({'view': 'day', 'days': []});
      expect(agenda.overdue, isEmpty);
      expect(agenda.unscheduled, isEmpty);
    });
  });

  group('CalendarCell', () {
    test('a day with neither task nor capture is empty', () {
      final cell = CalendarCell.fromJson({'day': '2026-06-08'});
      expect(cell.isEmpty, isTrue);
    });

    test('a day with only a capture is not empty', () {
      final cell = CalendarCell.fromJson({'day': '2026-06-08', 'captures': 2});
      expect(cell.isEmpty, isFalse);
    });
  });

  group('Reminder', () {
    test('distinguishes automatic from manual', () {
      // The distinction is load-bearing: automatic reminders are rewritten when
      // the deadline moves, manual ones never are.
      final automatic = Reminder.fromJson({
        'id': 'r1',
        'remind_at': '2026-06-12T07:45:00Z',
        'status': 'scheduled',
        'offset_rule': '-15m',
      });
      final manual = Reminder.fromJson({
        'id': 'r2',
        'remind_at': '2026-06-12T07:45:00Z',
        'status': 'scheduled',
      });

      expect(automatic.isAutomatic, isTrue);
      expect(manual.isAutomatic, isFalse);
    });

    test('only a scheduled reminder is pending', () {
      for (final status in ['sent', 'cancelled', 'dismissed', 'failed']) {
        final reminder = Reminder.fromJson({
          'id': 'r',
          'remind_at': '2026-06-12T07:45:00Z',
          'status': status,
        });
        expect(reminder.isPending, isFalse, reason: status);
      }
    });

    test('maps an unknown status rather than throwing', () {
      expect(reminderStatusFrom('quarantined'), ReminderStatus.unknown);
    });
  });

  group('AppNotification', () {
    test('unread when never read', () {
      final notification = AppNotification.fromJson({
        'id': 'n1',
        'kind': 'reminder',
        'title': 'Rappeler le DAF',
        'created_at': '2026-06-10T08:00:00Z',
      });
      expect(notification.unread, isTrue);
      expect(notification.kind, NotificationKind.reminder);
    });

    test('maps an unknown kind rather than throwing', () {
      expect(notificationKindFrom('newsletter'), NotificationKind.unknown);
    });
  });

  group('ParsedQuery', () {
    test('reports the tokens the server ignored', () {
      final query = ParsedQuery.fromJson({
        'text': 'DAF',
        'types': ['task'],
        'ignored': ['p:hgih'],
      });
      expect(query.hasFilters, isTrue);
      expect(query.ignored, ['p:hgih']);
    });

    test('free text alone is not a filter', () {
      final query = ParsedQuery.fromJson({'text': 'budget'});
      expect(query.hasFilters, isFalse);
    });
  });

  group('Statistics', () {
    test('converts the AI cost from micro-euros', () {
      final stats = Statistics.fromJson({
        'window_days': 30,
        'streak': {'current': 3, 'longest': 9},
        'ai_cost_micro_eur': 1250000,
      });
      expect(stats.aiCostEur, closeTo(1.25, 0.001));
      expect(stats.streak.current, 3);
    });

    test('survives a response carrying only the required fields', () {
      final stats = Statistics.fromJson({'window_days': 7, 'streak': {}});
      expect(stats.daily, isEmpty);
      expect(stats.completionRate, 0);
      expect(stats.byType, isEmpty);
    });
  });

  group('ProjectDetail', () {
    test('derives the completed count and progress', () {
      final project = ProjectDetail.fromJson({
        'id': 'p1',
        'name': 'Refonte',
        'slug': 'refonte',
        'open_count': 3,
        'total_count': 10,
      });
      expect(project.doneCount, 7);
      expect(project.progress, closeTo(0.7, 0.001));
    });

    test('an empty project has zero progress, not NaN', () {
      final project = ProjectDetail.fromJson({
        'id': 'p1',
        'name': 'Vide',
        'slug': 'vide',
      });
      expect(project.progress, 0);
    });
  });

  group('Entry with phase-2 fields', () {
    test('reads pinning and recurrence', () {
      final entry = Entry.fromJson({
        'id': 'e1',
        'entry_type': 'task',
        'title': 'Réunion hebdo',
        'status': 'active',
        'pinned_at': '2026-06-10T08:00:00Z',
        'project_id': 'p1',
        'task': {'recurrence_rule': 'FREQ=WEEKLY;BYDAY=MO', 'priority': 'high'},
      });

      expect(entry.pinnedAt, isNotNull);
      expect(entry.projectId, 'p1');
      expect(entry.task?.recurrenceRule, 'FREQ=WEEKLY;BYDAY=MO');
    });

    test('a phase-1 payload still parses', () {
      // The client must keep working against a server that has not shipped the
      // new fields yet — deploys are not atomic.
      final entry = Entry.fromJson({
        'id': 'e1',
        'entry_type': 'note',
        'title': 'Ancienne note',
        'status': 'active',
      });
      expect(entry.pinnedAt, isNull);
      expect(entry.projectId, isNull);
    });
  });

  group('ActivityEvent', () {
    test('keeps the denormalised label', () {
      final event = ActivityEvent.fromJson({
        'id': 12,
        'action': 'completed',
        'subject_label': 'Rappeler le DAF',
        'occurred_at': '2026-06-10T08:00:00Z',
      });
      expect(event.subjectLabel, 'Rappeler le DAF');
      expect(event.bySystem, isFalse);
    });

    test('flags system-authored events', () {
      final event = ActivityEvent.fromJson({
        'id': 13,
        'action': 'recurred',
        'actor_type': 'system',
        'occurred_at': '2026-06-10T08:00:00Z',
      });
      expect(event.bySystem, isTrue);
    });
  });
}
