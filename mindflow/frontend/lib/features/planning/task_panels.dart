/// The panels the entry detail screen gained in phase 2: subtasks, reminders,
/// recurrence and the per-entry timeline.
///
/// Kept out of `note_detail_screen.dart` so that file stays about *the entry*
/// and these stay about *acting on it*. They are also each embeddable
/// separately, which the wide layout uses.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/errors.dart';
import '../../core/api/models.dart';
import '../../core/api/planning_models.dart';
import '../../core/design/components.dart';
import '../../core/design/theme.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import 'planning_providers.dart';
import 'timeline_screen.dart';

// --------------------------------------------------------------------------- //
// Subtasks
// --------------------------------------------------------------------------- //
class SubtaskPanel extends ConsumerStatefulWidget {
  const SubtaskPanel({required this.entryId, super.key});

  final String entryId;

  @override
  ConsumerState<SubtaskPanel> createState() => _SubtaskPanelState();
}

class _SubtaskPanelState extends ConsumerState<SubtaskPanel> {
  final _controller = TextEditingController();
  final _focus = FocusNode();
  bool _adding = false;

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    final title = _controller.text.trim();
    if (title.isEmpty) return;

    final messenger = ScaffoldMessenger.of(context);
    setState(() => _adding = true);
    try {
      await ref.read(planningActionsProvider).addSubtask(widget.entryId, title);
      _controller.clear();
      // Keep the focus in the field: adding a checklist is a burst of typing,
      // and having to click back into the box between items is friction nobody
      // tolerates twice.
      _focus.requestFocus();
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    } finally {
      if (mounted) setState(() => _adding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final subtasks = ref.watch(subtasksProvider(widget.entryId));

    return subtasks.when(
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(vertical: Space.md),
        child: MfSkeleton(width: 180),
      ),
      error: (_, __) => const SizedBox.shrink(),
      data: (items) {
        final done = items.where((item) => item.done).length;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            MfSectionHeader(
              title: 'Sous-tâches',
              action: items.isEmpty
                  ? null
                  : Text(
                      '$done/${items.length}',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
            ),
            if (items.isNotEmpty) ...[
              MfProgressBar(value: done / items.length),
              const SizedBox(height: Space.sm),
            ],
            for (final subtask in items)
              _SubtaskRow(key: ValueKey(subtask.id), subtask: subtask),
            const SizedBox(height: Space.xs),
            Row(
              children: [
                const SizedBox(width: 2),
                Icon(
                  Icons.add,
                  size: 16,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
                const SizedBox(width: Space.sm),
                Expanded(
                  child: TextField(
                    key: const Key('subtask_input'),
                    controller: _controller,
                    focusNode: _focus,
                    enabled: !_adding,
                    onSubmitted: (_) => _add(),
                    style: Theme.of(context).textTheme.bodyMedium,
                    decoration: const InputDecoration(
                      hintText: 'Ajouter une sous-tâche…',
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      filled: false,
                      isDense: true,
                      contentPadding: EdgeInsets.symmetric(vertical: Space.sm),
                    ),
                  ),
                ),
              ],
            ),
          ],
        );
      },
    );
  }
}

class _SubtaskRow extends ConsumerWidget {
  const _SubtaskRow({required this.subtask, super.key});

  final Subtask subtask;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return Dismissible(
      key: ValueKey('dismiss-${subtask.id}'),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: Space.md),
        child: Icon(Icons.delete_outline, size: 16, color: scheme.error),
      ),
      onDismissed: (_) =>
          ref.read(planningActionsProvider).deleteSubtask(subtask),
      child: InkWell(
        onTap: () => ref.read(planningActionsProvider).toggleSubtask(subtask),
        borderRadius: Radii.smAll,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: Space.xs),
          child: Row(
            children: [
              Icon(
                subtask.done ? Icons.check_box : Icons.check_box_outline_blank,
                size: 16,
                color: subtask.done ? scheme.primary : scheme.outline,
              ),
              const SizedBox(width: Space.sm),
              Expanded(
                child: Text(
                  subtask.title,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    decoration:
                        subtask.done ? TextDecoration.lineThrough : null,
                    color: subtask.done ? scheme.onSurfaceVariant : null,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// --------------------------------------------------------------------------- //
// Reminders
// --------------------------------------------------------------------------- //
class ReminderPanel extends ConsumerWidget {
  const ReminderPanel({required this.entryId, super.key});

  final String entryId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final reminders = ref.watch(remindersProvider(entryId));

    return reminders.when(
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
      data: (items) {
        final pending = items.where((item) => item.isPending).toList();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            MfSectionHeader(
              title: 'Rappels',
              action: TextButton.icon(
                onPressed: () => _addReminder(context, ref),
                icon: const Icon(Icons.add, size: 14),
                label: const Text('Ajouter'),
              ),
            ),
            if (pending.isEmpty)
              Text(
                'Aucun rappel programmé.',
                style: Theme.of(context).textTheme.bodySmall,
              )
            else
              for (final reminder in pending)
                _ReminderRow(key: ValueKey(reminder.id), reminder: reminder),
          ],
        );
      },
    );
  }

  Future<void> _addReminder(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    final now = DateTime.now();

    final date = await showDatePicker(
      context: context,
      initialDate: now.add(const Duration(days: 1)),
      firstDate: now,
      lastDate: now.add(const Duration(days: 730)),
    );
    if (date == null || !context.mounted) return;

    final time = await showTimePicker(
      context: context,
      initialTime: const TimeOfDay(hour: 9, minute: 0),
    );
    if (time == null) return;

    final moment =
        DateTime(date.year, date.month, date.day, time.hour, time.minute);
    try {
      await ref.read(planningActionsProvider).addReminder(entryId, moment);
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }
}

class _ReminderRow extends ConsumerWidget {
  const _ReminderRow({required this.reminder, super.key});

  final Reminder reminder;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: Space.xs),
      child: Row(
        children: [
          Icon(
            reminder.channel == 'local'
                ? Icons.desktop_windows_outlined
                : Icons.notifications_none,
            size: 15,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(width: Space.sm),
          Expanded(
            child: Text(
              formatDue(reminder.remindAt, precision: 'minute'),
              style: theme.textTheme.bodySmall,
            ),
          ),
          if (reminder.isAutomatic)
            // Automatic reminders follow the deadline; manual ones do not. Said
            // plainly so nobody is surprised when one moves and the other does
            // not.
            const MfChip(label: 'auto'),
          IconButton(
            tooltip: 'Annuler',
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.close, size: 14),
            onPressed: () =>
                ref.read(planningActionsProvider).cancelReminder(reminder.id),
          ),
        ],
      ),
    );
  }
}

// --------------------------------------------------------------------------- //
// Priority, recurrence, snooze
// --------------------------------------------------------------------------- //
class TaskControls extends ConsumerWidget {
  const TaskControls({required this.entry, super.key});

  final Entry entry;

  static const _rules = <(String, String?)>[
    ('Aucune', null),
    ('Tous les jours', 'FREQ=DAILY'),
    ('Toutes les semaines', 'FREQ=WEEKLY'),
    ('Tous les lundis', 'FREQ=WEEKLY;BYDAY=MO'),
    ('Tous les mois', 'FREQ=MONTHLY'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final task = entry.task;

    return Wrap(
      spacing: Space.sm,
      runSpacing: Space.sm,
      children: [
        MfChip(
          label: priorityLabel(task?.priority ?? 'normal'),
          icon: priorityIcon(task?.priority ?? 'normal'),
          color: priorityColor(scheme, task?.priority ?? 'normal'),
          onTap: () => _pickPriority(context, ref),
        ),
        MfChip(
          label:
              task?.recurrenceRule == null ? 'Ne se répète pas' : 'Récurrent',
          icon: Icons.repeat,
          selected: task?.recurrenceRule != null,
          onTap: () => _pickRecurrence(context, ref),
        ),
        MfChip(
          label: 'Reporter',
          icon: Icons.snooze,
          onTap: () => _snooze(context, ref),
        ),
        MfChip(
          label: entry.pinnedAt == null ? 'Épingler' : 'Épinglé',
          icon: Icons.push_pin_outlined,
          selected: entry.pinnedAt != null,
          onTap: () => ref
              .read(planningActionsProvider)
              .pin(entry.id, pinned: entry.pinnedAt == null),
        ),
      ],
    );
  }

  Future<void> _pickPriority(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    final choice = await showModalBottomSheet<String>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final value in ['urgent', 'high', 'normal', 'low'])
              ListTile(
                leading: Icon(priorityIcon(value), size: 18),
                title: Text(priorityLabel(value)),
                onTap: () => Navigator.of(context).pop(value),
              ),
          ],
        ),
      ),
    );
    if (choice == null) return;
    try {
      await ref
          .read(planningActionsProvider)
          .bulkUpdate([entry.id], priority: choice);
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }

  Future<void> _pickRecurrence(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    final choice = await showModalBottomSheet<String?>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final (label, rule) in _rules)
              ListTile(
                leading: const Icon(Icons.repeat, size: 18),
                title: Text(label),
                onTap: () => Navigator.of(context).pop(rule ?? ''),
              ),
          ],
        ),
      ),
    );
    if (choice == null) return;
    try {
      await ref
          .read(planningActionsProvider)
          .setRecurrence(entry.id, choice.isEmpty ? null : choice);
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }

  Future<void> _snooze(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    final now = DateTime.now();
    final options = <(String, DateTime)>[
      ('Ce soir', DateTime(now.year, now.month, now.day, 19)),
      ('Demain matin', DateTime(now.year, now.month, now.day + 1, 9)),
      ('La semaine prochaine', DateTime(now.year, now.month, now.day + 7, 9)),
    ];

    final choice = await showModalBottomSheet<DateTime>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(Space.md),
              child: MfNotice(
                icon: Icons.info_outline,
                message: "Reporter masque la tâche. L'échéance ne bouge pas.",
              ),
            ),
            for (final (label, moment) in options)
              if (moment.isAfter(now))
                ListTile(
                  leading: const Icon(Icons.snooze, size: 18),
                  title: Text(label),
                  subtitle: Text(formatDue(moment, precision: 'minute')),
                  onTap: () => Navigator.of(context).pop(moment),
                ),
          ],
        ),
      ),
    );
    if (choice == null) return;
    try {
      await ref.read(planningActionsProvider).snooze(entry.id, choice);
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }
}

// --------------------------------------------------------------------------- //
// Per-entry history
// --------------------------------------------------------------------------- //
class EntryHistoryPanel extends ConsumerWidget {
  const EntryHistoryPanel({required this.entryId, super.key});

  final String entryId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final events = ref.watch(activityProvider(entryId));

    return events.maybeWhen(
      data: (data) => data.isEmpty
          ? const SizedBox.shrink()
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const MfSectionHeader(title: 'Historique'),
                TimelineList(events: data, shrinkWrap: true),
              ],
            ),
      orElse: () => const SizedBox.shrink(),
    );
  }
}
