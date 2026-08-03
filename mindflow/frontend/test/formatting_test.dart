import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:mindflow/core/ui/formatting.dart';

void main() {
  setUpAll(() async {
    await initializeDateFormatting('fr_FR');
  });

  group('formatDuration', () {
    test('pads seconds', () {
      expect(formatDuration(const Duration(seconds: 5)), '0:05');
      expect(formatDuration(const Duration(minutes: 2, seconds: 30)), '2:30');
    });

    test('keeps counting past an hour rather than wrapping', () {
      // A 75-minute capture must not read "15:00".
      expect(formatDuration(const Duration(minutes: 75)), '75:00');
    });
  });

  group('formatDay', () {
    final now = DateTime(2026, 6, 10, 14, 30);

    test('uses calendar days, not 24-hour spans', () {
      // 23:00 today and 08:00 tomorrow are nine hours apart but one day apart.
      final lateTonight = DateTime(2026, 6, 10, 23);
      final tomorrowMorning = DateTime(2026, 6, 11, 8);
      expect(formatDay(lateTonight, now: now), "aujourd'hui");
      expect(formatDay(tomorrowMorning, now: lateTonight), 'demain');
    });

    test('names the weekday inside the coming week', () {
      expect(formatDay(DateTime(2026, 6, 13), now: now), 'samedi');
    });

    test('falls back to an absolute date beyond a week', () {
      expect(formatDay(DateTime(2026, 7, 20), now: now), '20 juillet');
    });

    test('includes the year once it differs', () {
      expect(formatDay(DateTime(2027, 1, 5), now: now), '5 janvier 2027');
    });
  });

  group('formatDue', () {
    final now = DateTime(2026, 6, 10, 9);

    test('shows an hour only when the resolution had one', () {
      final due = DateTime(2026, 6, 11, 14);
      expect(formatDue(due, precision: 'hour', now: now), 'demain à 14:00');
      // "jeudi" resolves to a day: inventing 14:00 would claim a precision the
      // user never gave (ADR-020).
      expect(formatDue(due, precision: 'day', now: now), 'demain');
    });

    test('states a week or a month as such', () {
      expect(
        formatDue(DateTime(2026, 6, 22), precision: 'week', now: now),
        'semaine du 22 juin',
      );
      expect(
        formatDue(DateTime(2026, 9, 30), precision: 'month', now: now),
        'septembre 2026',
      );
    });

    test('is empty without a date', () {
      expect(formatDue(null), '');
    });
  });

  group('isOverdue', () {
    test('is false without a due date', () {
      expect(isOverdue(null), isFalse);
    });

    test('compares against the given instant', () {
      final now = DateTime(2026, 6, 10, 12);
      expect(isOverdue(DateTime(2026, 6, 10, 11), now: now), isTrue);
      expect(isOverdue(DateTime(2026, 6, 10, 13), now: now), isFalse);
    });
  });

  group('formatTimestamp', () {
    test('collapses the last hour to minutes', () {
      final now = DateTime(2026, 6, 10, 12);
      expect(formatTimestamp(DateTime(2026, 6, 10, 11, 45), now: now),
          'il y a 15 min');
      expect(formatTimestamp(DateTime(2026, 6, 10, 11, 59, 50), now: now),
          "à l'instant");
    });
  });
}
