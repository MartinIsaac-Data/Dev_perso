/// Human-readable dates and durations, in French.
///
/// Deliberately shows *relative* wording near today ("demain", "dans 3 jours")
/// and absolute dates further out. A due date the user cannot situate at a
/// glance is a due date they will not act on.
library;

import 'package:intl/intl.dart';

const _locale = 'fr_FR';

String formatDuration(Duration duration) {
  final minutes = duration.inMinutes;
  final seconds = duration.inSeconds % 60;
  return '$minutes:${seconds.toString().padLeft(2, '0')}';
}

String formatDurationMs(int milliseconds) =>
    formatDuration(Duration(milliseconds: milliseconds));

/// Calendar-day difference, not a 24-hour count: at 23:00, "tomorrow at 08:00"
/// is one day away, not zero.
int _dayDelta(DateTime from, DateTime to) {
  final a = DateTime(from.year, from.month, from.day);
  final b = DateTime(to.year, to.month, to.day);
  return b.difference(a).inDays;
}

String formatDay(DateTime date, {DateTime? now}) {
  final reference = now ?? DateTime.now();
  final delta = _dayDelta(reference, date.toLocal());
  return switch (delta) {
    0 => "aujourd'hui",
    1 => 'demain',
    -1 => 'hier',
    _ when delta > 1 && delta < 7 =>
      DateFormat.EEEE(_locale).format(date.toLocal()),
    _ when delta < -1 && delta > -7 => 'il y a ${-delta} jours',
    _ when date.year == reference.year =>
      DateFormat('d MMMM', _locale).format(date.toLocal()),
    _ => DateFormat('d MMMM yyyy', _locale).format(date.toLocal()),
  };
}

/// Due dates carry a precision (`day`, `hour`, `week`, `month`): showing
/// "14:00" for something the user said as "jeudi" would invent a certainty the
/// resolution never had (ADR-020).
String formatDue(DateTime? dueAt, {String? precision, DateTime? now}) {
  if (dueAt == null) return '';
  final local = dueAt.toLocal();
  final day = formatDay(local, now: now);
  return switch (precision) {
    'hour' || 'minute' => '$day à ${DateFormat.Hm(_locale).format(local)}',
    'week' => 'semaine du ${DateFormat('d MMMM', _locale).format(local)}',
    'month' => DateFormat('MMMM yyyy', _locale).format(local),
    _ => day,
  };
}

String formatTimestamp(DateTime moment, {DateTime? now}) {
  final local = moment.toLocal();
  final reference = now ?? DateTime.now();
  final elapsed = reference.difference(local);
  if (elapsed.inMinutes < 1) return "à l'instant";
  if (elapsed.inMinutes < 60) return 'il y a ${elapsed.inMinutes} min';
  if (_dayDelta(reference, local) == 0) {
    return DateFormat.Hm(_locale).format(local);
  }
  return '${formatDay(local, now: reference)} à ${DateFormat.Hm(_locale).format(local)}';
}

bool isOverdue(DateTime? dueAt, {DateTime? now}) {
  if (dueAt == null) return false;
  return dueAt.toLocal().isBefore(now ?? DateTime.now());
}
