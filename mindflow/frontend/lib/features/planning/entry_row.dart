/// The entry row, used by every list in the product.
///
/// This widget is on the hot path — the agenda, search results and the task list
/// all build sixty of them per screenful — so its construction is deliberately
/// cheap:
///
/// * a **fixed height** (`Layout.entryRowHeight`), which lets the enclosing
///   `ListView` use `itemExtent` and compute scroll geometry without laying out
///   off-screen children;
/// * **no `Opacity`, no shadows, no clip** — each of those forces a save layer,
///   and a save layer per row is how a list drops frames on a mid-range phone;
/// * `const` sub-widgets wherever the data allows, so rebuilds skip them.
library;

import 'package:flutter/material.dart';

import '../../core/api/models.dart';
import '../../core/api/planning_models.dart';
import '../../core/design/components.dart';
import '../../core/design/theme.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';

class EntryRow extends StatelessWidget {
  const EntryRow({
    required this.entry,
    this.subtasks,
    this.onTap,
    this.onToggle,
    this.selected = false,
    this.selectable = false,
    this.showDay = false,
    super.key,
  });

  final Entry entry;
  final SubtaskProgress? subtasks;
  final VoidCallback? onTap;
  final VoidCallback? onToggle;
  final bool selected;
  final bool selectable;
  final bool showDay;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isTask = entry.type == EntryType.task;
    final isDone = entry.status == EntryStatus.done;
    final due = entry.task?.dueAt;
    final overdue = !isDone && isOverdue(due);

    return SizedBox(
      height: Layout.entryRowHeight,
      child: InkWell(
        onTap: onTap,
        borderRadius: Radii.mdAll,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: Space.sm),
          decoration: BoxDecoration(
            color: selected ? scheme.primaryContainer : Colors.transparent,
            borderRadius: Radii.mdAll,
          ),
          child: Row(
            children: [
              _Leading(
                entry: entry,
                isTask: isTask,
                isDone: isDone,
                selectable: selectable,
                selected: selected,
                onToggle: onToggle,
              ),
              const SizedBox(width: Space.md),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      entry.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        // Struck through rather than faded: a `TextDecoration`
                        // costs nothing, while an `Opacity` wrapper forces a
                        // save layer on every completed row.
                        decoration: isDone ? TextDecoration.lineThrough : null,
                        color:
                            isDone ? scheme.onSurfaceVariant : scheme.onSurface,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 3),
                    _MetaLine(
                      entry: entry,
                      subtasks: subtasks,
                      overdue: overdue,
                      showDay: showDay,
                    ),
                  ],
                ),
              ),
              if (entry.pinnedAt != null)
                Icon(Icons.push_pin, size: 13, color: scheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}

class _Leading extends StatelessWidget {
  const _Leading({
    required this.entry,
    required this.isTask,
    required this.isDone,
    required this.selectable,
    required this.selected,
    required this.onToggle,
  });

  final Entry entry;
  final bool isTask;
  final bool isDone;
  final bool selectable;
  final bool selected;
  final VoidCallback? onToggle;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    if (selectable) {
      return SizedBox(
        width: 28,
        child: Icon(
          selected ? Icons.check_box : Icons.check_box_outline_blank,
          size: 18,
          color: selected ? scheme.primary : scheme.outline,
        ),
      );
    }

    if (isTask && onToggle != null) {
      return SizedBox(
        width: 28,
        child: IconButton(
          onPressed: onToggle,
          padding: EdgeInsets.zero,
          visualDensity: VisualDensity.compact,
          tooltip: isDone ? 'Rouvrir' : 'Terminer',
          icon: Icon(
            isDone ? Icons.check_circle : Icons.circle_outlined,
            size: 18,
            color: isDone ? scheme.primary : scheme.outline,
          ),
        ),
      );
    }

    return SizedBox(
      width: 28,
      child: Icon(
        entryIcon(entry.type),
        size: 16,
        color: entryColor(scheme, entry.type),
      ),
    );
  }
}

/// The second line: type, deadline, priority, tags, subtask progress.
///
/// Built as a `Row` of pre-sized pieces rather than a `Wrap`: at a fixed row
/// height nothing can wrap anyway, and `Wrap` costs an extra layout pass per
/// row for a flexibility this design does not use.
class _MetaLine extends StatelessWidget {
  const _MetaLine({
    required this.entry,
    required this.subtasks,
    required this.overdue,
    required this.showDay,
  });

  final Entry entry;
  final SubtaskProgress? subtasks;
  final bool overdue;
  final bool showDay;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final task = entry.task;
    final pieces = <Widget>[];

    pieces.add(MfMeta(
      label: entryTypeLabel(entry.type),
      color: entryColor(scheme, entry.type),
    ));

    if (task?.dueAt != null) {
      pieces.add(MfMeta(
        icon: overdue ? Icons.error_outline : Icons.schedule,
        label: showDay
            ? formatDue(task!.dueAt, precision: task.duePrecision)
            : formatTimeOnly(task!.dueAt!),
        color: overdue ? scheme.error : null,
      ));
    }

    final priority = task?.priority ?? 'normal';
    if (priority != 'normal') {
      pieces.add(MfMeta(
        icon: priorityIcon(priority),
        label: priorityLabel(priority),
        color: priorityColor(scheme, priority),
      ));
    }

    if (subtasks != null && subtasks!.any) {
      pieces.add(MfMeta(
        icon: Icons.checklist,
        label: '${subtasks!.done}/${subtasks!.total}',
        color: subtasks!.complete ? scheme.primary : null,
      ));
    }

    if (task?.recurrenceRule != null) {
      pieces.add(const MfMeta(icon: Icons.repeat, label: ''));
    }

    for (final tag in entry.tags.take(2)) {
      pieces.add(MfMeta(label: '#$tag'));
    }

    if (entry.needsReview) {
      pieces.add(MfMeta(
        icon: Icons.help_outline,
        label: 'À vérifier',
        color: scheme.tertiary,
      ));
    }

    return Row(
      children: [
        for (var index = 0; index < pieces.length; index++) ...[
          if (index > 0) const SizedBox(width: Space.sm),
          Flexible(child: pieces[index]),
        ],
      ],
    );
  }
}
