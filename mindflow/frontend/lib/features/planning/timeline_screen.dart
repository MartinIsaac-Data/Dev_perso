/// History / Timeline — what happened, in the user's own terms.
///
/// Distinct from the audit log (a security record nobody browses) and from the
/// correction events (a model-quality signal). This one answers "what happened
/// to my task?", and its vocabulary is chosen for that question.
///
/// Events keep a denormalised label, so the timeline still reads correctly after
/// its subject is deleted. A history that goes blank is not a history.
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
import 'planning_providers.dart';

class TimelineScreen extends ConsumerWidget {
  const TimelineScreen({super.key, this.entryId});

  /// When set, the timeline of a single entry — shown inside its detail screen.
  final String? entryId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final events = ref.watch(activityProvider(entryId));

    return Scaffold(
      appBar: AppBar(title: const Text('Historique')),
      body: events.when(
        loading: () => const MfSkeletonList(),
        error: (error, _) => MfEmpty(
          icon: Icons.history,
          title: 'Historique indisponible',
          message: error is ApiException ? error.userMessage : null,
        ),
        data: (data) => data.isEmpty
            ? const MfEmpty(
                icon: Icons.history,
                title: 'Rien encore',
                message: 'Vos actions apparaîtront ici.',
              )
            : MfContentColumn(child: TimelineList(events: data)),
      ),
    );
  }
}

/// The list itself, extracted so the entry detail screen can embed it.
class TimelineList extends StatelessWidget {
  const TimelineList(
      {required this.events, this.shrinkWrap = false, super.key});

  final List<ActivityEvent> events;
  final bool shrinkWrap;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      shrinkWrap: shrinkWrap,
      physics: shrinkWrap ? const NeverScrollableScrollPhysics() : null,
      padding: const EdgeInsets.symmetric(vertical: Space.md),
      itemCount: events.length,
      itemBuilder: (context, index) => _TimelineTile(
        key: ValueKey(events[index].id),
        event: events[index],
        // The connector is drawn between events, so the last one has no tail.
        isLast: index == events.length - 1,
      ),
    );
  }
}

class _TimelineTile extends StatelessWidget {
  const _TimelineTile({required this.event, required this.isLast, super.key});

  final ActivityEvent event;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final (icon, color, verb) = _describe(event, scheme);

    return InkWell(
      onTap: event.entryId == null
          ? null
          : () => context.push(Routes.note(event.entryId!)),
      borderRadius: Radii.mdAll,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // The rail: a dot and the line joining it to the next event.
            SizedBox(
              width: 32,
              child: Column(
                children: [
                  const SizedBox(height: Space.md),
                  Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      color: scheme.surfaceContainer,
                      shape: BoxShape.circle,
                      border: Border.all(color: scheme.outlineVariant),
                    ),
                    child: Icon(icon, size: 11, color: color),
                  ),
                  if (!isLast)
                    Expanded(
                      child: Container(width: 1, color: scheme.outlineVariant),
                    ),
                ],
              ),
            ),
            const SizedBox(width: Space.md),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(top: Space.md, bottom: Space.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                              text: verb, style: theme.textTheme.bodySmall),
                          if (event.subjectLabel != null) ...[
                            const TextSpan(text: ' '),
                            TextSpan(
                              text: event.subjectLabel,
                              style: theme.textTheme.bodyMedium?.copyWith(
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ],
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        MfMeta(label: formatRelativePast(event.occurredAt)),
                        if (event.bySystem) ...[
                          const SizedBox(width: Space.sm),
                          const MfMeta(
                              icon: Icons.smart_toy_outlined, label: 'auto'),
                        ],
                        if (_detailLine(event) != null) ...[
                          const SizedBox(width: Space.sm),
                          MfMeta(label: _detailLine(event)!),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// The verb, in French and in the past tense, because that is how a history
  /// reads. Unknown actions get a neutral wording rather than the raw key —
  /// the server may add actions this build does not know (API.md §12.2).
  static (IconData, Color, String) _describe(
          ActivityEvent event, ColorScheme scheme) =>
      switch (event.action) {
        'created' => (Icons.add, scheme.primary, 'Créé'),
        'edited' => (Icons.edit_outlined, scheme.onSurfaceVariant, 'Modifié'),
        'completed' => (Icons.check, scheme.primary, 'Terminé'),
        'reopened' => (Icons.undo, scheme.onSurfaceVariant, 'Rouvert'),
        'archived' => (
            Icons.archive_outlined,
            scheme.onSurfaceVariant,
            'Archivé'
          ),
        'deleted' => (Icons.delete_outline, scheme.error, 'Supprimé'),
        'restored' => (Icons.restore, scheme.primary, 'Restauré'),
        'snoozed' => (Icons.snooze, scheme.tertiary, 'Reporté'),
        'rescheduled' => (Icons.event_repeat, scheme.tertiary, 'Replanifié'),
        'priority_changed' => (
            Icons.flag_outlined,
            scheme.tertiary,
            'Priorité modifiée'
          ),
        'project_changed' => (
            Icons.folder_outlined,
            scheme.tertiary,
            'Projet modifié'
          ),
        'tagged' => (Icons.sell_outlined, scheme.onSurfaceVariant, 'Tagué'),
        'untagged' => (
            Icons.sell_outlined,
            scheme.onSurfaceVariant,
            'Tag retiré'
          ),
        'subtask_added' => (
            Icons.checklist,
            scheme.onSurfaceVariant,
            'Sous-tâche ajoutée'
          ),
        'subtask_completed' => (
            Icons.check,
            scheme.primary,
            'Sous-tâche cochée'
          ),
        'reminder_set' => (
            Icons.notifications_none,
            scheme.tertiary,
            'Rappel programmé'
          ),
        'reminder_fired' => (
            Icons.notifications_active_outlined,
            scheme.tertiary,
            'Rappel envoyé'
          ),
        'recurred' => (
            Icons.repeat,
            scheme.primary,
            'Occurrence suivante créée'
          ),
        'captured' => (Icons.graphic_eq, scheme.primary, 'Capturé'),
        _ => (Icons.circle_outlined, scheme.onSurfaceVariant, 'Action'),
      };

  static String? _detailLine(ActivityEvent event) {
    final detail = event.detail;
    if (event.action == 'priority_changed') {
      return '${detail['from']} → ${detail['to']}';
    }
    if (event.action == 'subtask_added' ||
        event.action == 'subtask_completed') {
      return detail['title'] as String?;
    }
    return null;
  }
}
