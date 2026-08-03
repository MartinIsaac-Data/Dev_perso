/// Calendar — a month at a glance.
///
/// The grid is a `CustomPaint`-free layout of plain containers: forty-two cells
/// is few enough that widgets are cheaper than a painter, and widgets keep
/// hit-testing and semantics for free.
///
/// Density is shown by **dots, not numbers**. A number in a 40-pixel cell is
/// unreadable at a glance and the question the month view answers is "which days
/// are heavy?", not "exactly how many". Overdue days get a ring instead of a
/// different colour, so the signal survives a greyscale screenshot and a
/// colour-blind reader.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/errors.dart';
import '../../core/api/planning_models.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import 'planning_providers.dart';

class CalendarScreen extends ConsumerWidget {
  const CalendarScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final month = ref.watch(calendarMonthProvider);
    final calendar = ref.watch(calendarProvider(month));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Calendrier'),
        actions: [
          IconButton(
            tooltip: 'Mois précédent',
            onPressed: () => ref.read(calendarMonthProvider.notifier).state =
                DateTime(month.year, month.month - 1),
            icon: const Icon(Icons.chevron_left, size: 18),
          ),
          IconButton(
            tooltip: 'Mois suivant',
            onPressed: () => ref.read(calendarMonthProvider.notifier).state =
                DateTime(month.year, month.month + 1),
            icon: const Icon(Icons.chevron_right, size: 18),
          ),
          const SizedBox(width: Space.sm),
        ],
      ),
      body: MfContentColumn(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: Space.md),
            Text(
              formatMonth(month),
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: Space.lg),
            const _WeekdayHeader(),
            const SizedBox(height: Space.sm),
            Expanded(
              child: calendar.when(
                loading: () => const _GridSkeleton(),
                error: (error, _) => MfEmpty(
                  icon: Icons.calendar_month_outlined,
                  title: 'Calendrier indisponible',
                  message: error is ApiException ? error.userMessage : null,
                ),
                data: (data) => _MonthGrid(month: month, cells: data.cells),
              ),
            ),
            const _Legend(),
            const SizedBox(height: Space.lg),
          ],
        ),
      ),
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        for (var weekday = 1; weekday <= 7; weekday++)
          Expanded(
            child: Center(
              child: Text(
                weekdayInitial(weekday),
                style: theme.textTheme.labelSmall,
              ),
            ),
          ),
      ],
    );
  }
}

class _MonthGrid extends ConsumerWidget {
  const _MonthGrid({required this.month, required this.cells});

  final DateTime month;
  final List<CalendarCell> cells;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final today = DateTime.now();
    final weeks = (cells.length / 7).ceil();

    return Column(
      children: [
        for (var week = 0; week < weeks; week++)
          Expanded(
            child: Row(
              children: [
                for (var day = 0; day < 7; day++)
                  Expanded(
                    child: () {
                      final index = week * 7 + day;
                      if (index >= cells.length) return const SizedBox.shrink();
                      final cell = cells[index];
                      return _DayCell(
                        cell: cell,
                        // Days from the neighbouring months are dimmed rather
                        // than hidden: an empty corner reads as a bug.
                        inMonth: cell.day.month == month.month,
                        isToday: cell.day.year == today.year &&
                            cell.day.month == today.month &&
                            cell.day.day == today.day,
                        onTap: () {
                          ref.read(agendaQueryProvider.notifier).state =
                              AgendaQuery(
                                  view: AgendaView.day, anchor: cell.day);
                        },
                      );
                    }(),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    required this.cell,
    required this.inMonth,
    required this.isToday,
    required this.onTap,
  });

  final CalendarCell cell;
  final bool inMonth;
  final bool isToday;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return InkWell(
      onTap: onTap,
      borderRadius: Radii.smAll,
      child: Container(
        margin: const EdgeInsets.all(2),
        padding: const EdgeInsets.all(Space.xs),
        decoration: BoxDecoration(
          borderRadius: Radii.smAll,
          color: isToday ? scheme.primaryContainer : null,
          // A ring, not a fill: the overdue signal survives greyscale.
          border: cell.overdue > 0
              ? Border.all(color: scheme.error, width: 1.2)
              : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${cell.day.day}',
              style: theme.textTheme.labelMedium?.copyWith(
                color: inMonth
                    ? (isToday ? scheme.onPrimaryContainer : scheme.onSurface)
                    : scheme.outline,
                fontWeight: isToday ? FontWeight.w700 : FontWeight.w500,
              ),
            ),
            const Spacer(),
            if (!cell.isEmpty) _Density(cell: cell),
          ],
        ),
      ),
    );
  }
}

/// Up to four dots. Beyond that a "+" — counting past four dots is slower than
/// reading the number, and the number is not the point of this view.
class _Density extends StatelessWidget {
  const _Density({required this.cell});

  final CalendarCell cell;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final pending = cell.pending.clamp(0, 4);
    final done = (cell.total - cell.pending).clamp(0, 4 - pending);

    return Row(
      children: [
        for (var index = 0; index < pending; index++)
          _Dot(color: cell.overdue > 0 ? scheme.error : scheme.primary),
        for (var index = 0; index < done; index++) _Dot(color: scheme.outline),
        if (cell.total > 4)
          Text(
            '+',
            style: TextStyle(
              fontSize: 9,
              height: 1,
              color: scheme.onSurfaceVariant,
            ),
          ),
        if (cell.captures > 0) ...[
          const SizedBox(width: 2),
          Icon(Icons.graphic_eq, size: 9, color: scheme.onSurfaceVariant),
        ],
      ],
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 4,
      height: 4,
      margin: const EdgeInsets.only(right: 2),
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Wrap(
      spacing: Space.lg,
      runSpacing: Space.sm,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _Dot(color: scheme.primary),
            const SizedBox(width: 4),
            const MfMeta(label: 'À faire'),
          ],
        ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _Dot(color: scheme.outline),
            const SizedBox(width: 4),
            const MfMeta(label: 'Terminé'),
          ],
        ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(2),
                border: Border.all(color: scheme.error, width: 1.2),
              ),
            ),
            const SizedBox(width: 4),
            const MfMeta(label: 'En retard'),
          ],
        ),
        const MfMeta(icon: Icons.graphic_eq, label: 'Enregistrement'),
      ],
    );
  }
}

class _GridSkeleton extends StatelessWidget {
  const _GridSkeleton();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (var week = 0; week < 6; week++)
          const Expanded(
            child: Padding(
              padding: EdgeInsets.all(2),
              child: MfSkeleton(height: double.infinity),
            ),
          ),
      ],
    );
  }
}
