/// One entry in a list.
///
/// Three things must be readable without tapping: what it is, when it is due,
/// and whether the AI was unsure. The third is the honest one — an extraction
/// the model hesitated on is shown as such rather than presented with the same
/// confidence as a certainty (PRD.md §8).
library;

import 'package:flutter/material.dart';

import '../../app/theme.dart';
import '../../core/api/models.dart';
import '../../core/ui/formatting.dart';

class EntryTile extends StatelessWidget {
  const EntryTile({
    required this.entry,
    this.onTap,
    this.onToggleDone,
    super.key,
  });

  final Entry entry;
  final VoidCallback? onTap;
  final VoidCallback? onToggleDone;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isTask = entry.type == EntryType.task;
    final isDone = entry.status == EntryStatus.done;
    final overdue = !isDone && isOverdue(entry.task?.dueAt);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (isTask && onToggleDone != null)
              Padding(
                padding: const EdgeInsets.only(right: 4),
                child: IconButton(
                  onPressed: onToggleDone,
                  visualDensity: VisualDensity.compact,
                  tooltip: isDone ? 'Rouvrir' : 'Marquer comme fait',
                  icon: Icon(
                    isDone ? Icons.check_circle : Icons.circle_outlined,
                    color: isDone ? scheme.primary : scheme.outline,
                  ),
                ),
              )
            else
              Padding(
                padding: const EdgeInsets.only(right: 12, top: 2, left: 8),
                child: Icon(
                  entryIcon(entry.type),
                  size: 20,
                  color: entryColor(scheme, entry.type),
                ),
              ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.title,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      decoration: isDone ? TextDecoration.lineThrough : null,
                      color: isDone ? scheme.onSurfaceVariant : null,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      _Meta(
                        label: entryTypeLabel(entry.type),
                        color: entryColor(scheme, entry.type),
                      ),
                      if (entry.task?.dueAt != null)
                        _Meta(
                          icon: Icons.schedule,
                          label: formatDue(
                            entry.task!.dueAt,
                            precision: entry.task!.duePrecision,
                          ),
                          color:
                              overdue ? scheme.error : scheme.onSurfaceVariant,
                        ),
                      if (entry.task?.priority == 'high' ||
                          entry.task?.priority == 'urgent')
                        _Meta(
                          icon: Icons.priority_high,
                          label: entry.task!.priority == 'urgent'
                              ? 'Urgent'
                              : 'Important',
                          color: scheme.error,
                        ),
                      for (final tag in entry.tags.take(3))
                        _Meta(label: '#$tag', color: scheme.onSurfaceVariant),
                      if (entry.needsReview)
                        _Meta(
                          icon: Icons.help_outline,
                          label: 'À vérifier',
                          color: scheme.tertiary,
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Meta extends StatelessWidget {
  const _Meta({required this.label, required this.color, this.icon});

  final String label;
  final Color color;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 3),
        ],
        Text(
          label,
          style: Theme.of(context)
              .textTheme
              .labelSmall
              ?.copyWith(color: color, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }
}
