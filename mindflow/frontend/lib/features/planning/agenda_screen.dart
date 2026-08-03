/// Agenda — what is due, day by day.
///
/// The screen is built from a `CustomScrollView` of slivers rather than nested
/// lists. That is not stylistic: a day with forty items inside a `Column` inside
/// a `ListView` lays out all forty even when two are visible, and a week of such
/// days is a screen that stutters on the first scroll. Slivers build only what
/// is on screen.
///
/// Overdue items sit in their own section at the top. Pinned to the day they
/// were due, they end up below the fold of a day nobody scrolls back to.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../core/api/errors.dart';
import '../../core/api/planning_models.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import 'entry_row.dart';
import 'planning_providers.dart';

class AgendaScreen extends ConsumerWidget {
  const AgendaScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final query = ref.watch(agendaQueryProvider);
    final agenda = ref.watch(agendaProvider(query));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Agenda'),
        actions: [
          const _ViewSwitcher(),
          const SizedBox(width: Space.sm),
          IconButton(
            tooltip: "Aujourd'hui",
            onPressed: () => ref.read(agendaQueryProvider.notifier).state =
                query.copyWith(anchor: DateTime.now()),
            icon: const Icon(Icons.today_outlined, size: 18),
          ),
          const SizedBox(width: Space.sm),
        ],
      ),
      body: Column(
        children: [
          _RangeBar(query: query),
          const Divider(height: 1),
          Expanded(
            child: agenda.when(
              loading: () => const MfSkeletonList(),
              error: (error, _) => MfEmpty(
                icon: Icons.cloud_off_outlined,
                title: 'Agenda indisponible',
                message: error is ApiException ? error.userMessage : null,
                action: FilledButton(
                  onPressed: () => ref.invalidate(agendaProvider(query)),
                  child: const Text('Réessayer'),
                ),
              ),
              data: (data) => _AgendaBody(agenda: data, query: query),
            ),
          ),
        ],
      ),
    );
  }
}

class _ViewSwitcher extends ConsumerWidget {
  const _ViewSwitcher();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Selects only the view field: switching day/week/month must not rebuild
    // the whole screen through the query object.
    final view = ref.watch(agendaQueryProvider.select((query) => query.view));
    return SegmentedButton<AgendaView>(
      segments: const [
        ButtonSegment(value: AgendaView.day, label: Text('Jour')),
        ButtonSegment(value: AgendaView.week, label: Text('Semaine')),
        ButtonSegment(value: AgendaView.month, label: Text('Mois')),
      ],
      selected: {view},
      showSelectedIcon: false,
      style: const ButtonStyle(visualDensity: VisualDensity.compact),
      onSelectionChanged: (selection) {
        final notifier = ref.read(agendaQueryProvider.notifier);
        notifier.state = notifier.state.copyWith(view: selection.first);
      },
    );
  }
}

class _RangeBar extends ConsumerWidget {
  const _RangeBar({required this.query});

  final AgendaQuery query;

  Duration get _step => switch (query.view) {
        AgendaView.day => const Duration(days: 1),
        AgendaView.week => const Duration(days: 7),
        AgendaView.month => const Duration(days: 30),
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final anchor = query.anchor ?? DateTime.now();
    final notifier = ref.read(agendaQueryProvider.notifier);

    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.sm),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Précédent',
            onPressed: () =>
                notifier.state = query.copyWith(anchor: anchor.subtract(_step)),
            icon: const Icon(Icons.chevron_left, size: 18),
          ),
          IconButton(
            tooltip: 'Suivant',
            onPressed: () =>
                notifier.state = query.copyWith(anchor: anchor.add(_step)),
            icon: const Icon(Icons.chevron_right, size: 18),
          ),
          const SizedBox(width: Space.sm),
          Text(formatDay(anchor), style: theme.textTheme.titleSmall),
          const Spacer(),
          MfChip(
            label: 'Terminées',
            icon: Icons.check_circle_outline,
            selected: query.includeDone,
            onTap: () => notifier.state =
                query.copyWith(includeDone: !query.includeDone),
          ),
          const SizedBox(width: Space.sm),
          MfChip(
            label: 'Sans échéance',
            icon: Icons.event_busy_outlined,
            selected: query.includeUnscheduled,
            onTap: () => notifier.state =
                query.copyWith(includeUnscheduled: !query.includeUnscheduled),
          ),
        ],
      ),
    );
  }
}

class _AgendaBody extends ConsumerWidget {
  const _AgendaBody({required this.agenda, required this.query});

  final Agenda agenda;
  final AgendaQuery query;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final populated = agenda.days.where((day) => day.items.isNotEmpty).toList();

    if (agenda.overdue.isEmpty &&
        populated.isEmpty &&
        agenda.unscheduled.isEmpty) {
      return const MfEmpty(
        icon: Icons.event_available_outlined,
        title: 'Rien de prévu',
        message: 'Aucune échéance sur cette période.',
      );
    }

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(agendaProvider(query));
        await ref.read(agendaProvider(query).future);
      },
      child: CustomScrollView(
        slivers: [
          if (agenda.overdue.isNotEmpty)
            _Section(
              title: 'En retard',
              count: agenda.overdue.length,
              tone: MfNoticeTone.danger,
              items: agenda.overdue,
              showDay: true,
            ),
          for (final day in populated)
            _Section(
              title: formatDay(day.day),
              count: day.items.length,
              items: day.items,
            ),
          if (agenda.unscheduled.isNotEmpty)
            _Section(
              title: 'Sans échéance',
              count: agenda.unscheduled.length,
              items: agenda.unscheduled,
            ),
          const SliverToBoxAdapter(child: SizedBox(height: Space.xxxl)),
        ],
      ),
    );
  }
}

class _Section extends ConsumerWidget {
  const _Section({
    required this.title,
    required this.count,
    required this.items,
    this.tone = MfNoticeTone.neutral,
    this.showDay = false,
  });

  final String title;
  final int count;
  final List<AgendaItem> items;
  final MfNoticeTone tone;
  final bool showDay;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    return SliverMainAxisGroup(
      slivers: [
        SliverPersistentHeader(
          pinned: true,
          delegate: _StickyHeader(
            title: title,
            count: count,
            background: scheme.surface,
            color: tone == MfNoticeTone.danger ? scheme.error : null,
          ),
        ),
        SliverFixedExtentList(
          itemExtent: Layout.entryRowHeight,
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              final item = items[index];
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: Space.md),
                child: EntryRow(
                  // A stable key so Flutter reuses the element when the list
                  // reorders instead of rebuilding every row below the change.
                  key: ValueKey(item.entry.id),
                  entry: item.entry,
                  subtasks: item.subtasks,
                  showDay: showDay,
                  onTap: () => context.push(Routes.note(item.entry.id)),
                  onToggle: () => _toggle(context, ref, item),
                ),
              );
            },
            childCount: items.length,
            findChildIndexCallback: (key) {
              final id = (key as ValueKey<String>).value;
              final index = items.indexWhere((item) => item.entry.id == id);
              return index < 0 ? null : index;
            },
          ),
        ),
      ],
    );
  }

  Future<void> _toggle(
      BuildContext context, WidgetRef ref, AgendaItem item) async {
    final messenger = ScaffoldMessenger.of(context);
    final actions = ref.read(planningActionsProvider);
    try {
      if (item.entry.status.name == 'done') {
        await actions.reopenTask(item.entry.id);
        return;
      }
      final (_, next) = await actions.completeTask(item.entry.id);
      if (next != null) {
        // Said at the moment of completion, which is when the user is looking:
        // a recurring task that silently regenerates is confusing.
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              'Prochaine occurrence : ${formatDue(next.task?.dueAt, precision: next.task?.duePrecision)}',
            ),
          ),
        );
      }
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }
}

/// A pinned section header. Sticky so the day a row belongs to is always
/// visible — without it, a long day scrolls its own title away and the dates
/// stop meaning anything.
class _StickyHeader extends SliverPersistentHeaderDelegate {
  _StickyHeader({
    required this.title,
    required this.count,
    required this.background,
    this.color,
  });

  final String title;
  final int count;
  final Color background;
  final Color? color;

  @override
  double get minExtent => 32;

  @override
  double get maxExtent => 32;

  @override
  Widget build(
      BuildContext context, double shrinkOffset, bool overlapsContent) {
    final theme = Theme.of(context);
    return Container(
      color: background,
      padding: const EdgeInsets.symmetric(horizontal: Space.lg),
      alignment: Alignment.centerLeft,
      child: Row(
        children: [
          Text(
            title.toUpperCase(),
            style: theme.textTheme.labelSmall?.copyWith(
              letterSpacing: 0.7,
              fontWeight: FontWeight.w600,
              color: color ?? theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(width: Space.sm),
          Text('$count', style: theme.textTheme.labelSmall),
        ],
      ),
    );
  }

  @override
  bool shouldRebuild(_StickyHeader oldDelegate) =>
      oldDelegate.title != title ||
      oldDelegate.count != count ||
      oldDelegate.color != color;
}
