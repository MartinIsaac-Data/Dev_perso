/// Home screen.
///
/// Answers one question — "what did I say, and what is now waiting for me?" —
/// and puts the record button within thumb reach. Everything else is one tap
/// away, never on this screen.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../core/api/models.dart';
import '../../core/auth/auth_controller.dart';
import '../capture/capture_controller.dart';
import '../notes/entry_tile.dart';
import '../notes/notes_providers.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    // Replay anything the previous session could not send. Done here rather
    // than at app start because it needs a signed-in user (ADR-009).
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(captureControllerProvider.notifier).flushPending();
    });
  }

  @override
  Widget build(BuildContext context) {
    final dashboard = ref.watch(dashboardProvider);
    final pending = ref.watch(captureControllerProvider).pendingCount;
    final user = ref.watch(currentUserProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('MindFlow'),
        actions: [
          IconButton(
            tooltip: 'Mes notes',
            onPressed: () => context.push(Routes.notes),
            icon: const Icon(Icons.list_alt_outlined),
          ),
          PopupMenuButton<String>(
            tooltip: 'Compte',
            icon: const Icon(Icons.account_circle_outlined),
            onSelected: (value) {
              if (value == 'signout') {
                ref.read(signInControllerProvider.notifier).signOut();
              }
            },
            itemBuilder: (context) => [
              PopupMenuItem<String>(
                enabled: false,
                child: Text(user?.email ?? 'Compte'),
              ),
              const PopupMenuDivider(),
              const PopupMenuItem<String>(
                value: 'signout',
                child: Text('Se déconnecter'),
              ),
            ],
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('dashboard_record'),
        onPressed: () => context.push(Routes.record),
        icon: const Icon(Icons.mic),
        label: const Text('Capturer'),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(dashboardProvider);
          await ref.read(dashboardProvider.future);
        },
        child: dashboard.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => _DashboardError(
            onRetry: () => ref.invalidate(dashboardProvider),
          ),
          data: (data) => ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
            children: [
              if (pending > 0) _PendingBanner(count: pending),
              _CounterRow(dashboard: data),
              const SizedBox(height: 24),
              _SectionTitle(
                title: 'À traiter',
                trailing: data.needsReview > 0 ? '${data.needsReview}' : null,
              ),
              if (data.needsReview == 0)
                const _EmptyLine('Rien à vérifier. Tout est classé.')
              else
                _NeedsReviewLink(count: data.needsReview),
              const SizedBox(height: 24),
              const _SectionTitle(title: 'Échéances proches'),
              if (data.dueSoon.isEmpty)
                const _EmptyLine('Aucune échéance dans les prochains jours.')
              else
                ...data.dueSoon.map(
                  (entry) => EntryTile(
                    entry: entry,
                    onTap: () => context.push(Routes.note(entry.id)),
                    onToggleDone: () =>
                        ref.read(entryActionsProvider).toggleDone(entry).then(
                              (_) => ref.invalidate(dashboardProvider),
                            ),
                  ),
                ),
              const SizedBox(height: 24),
              _QuotaLine(quota: data.quota),
            ],
          ),
        ),
      ),
    );
  }
}

class _CounterRow extends StatelessWidget {
  const _CounterRow({required this.dashboard});

  final Dashboard dashboard;

  @override
  Widget build(BuildContext context) {
    final byType = dashboard.entriesByType;
    return Row(
      children: [
        Expanded(
          child: _Counter(
            value: dashboard.captureCount,
            label: 'captures',
            icon: Icons.graphic_eq,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _Counter(
            value: byType['task'] ?? 0,
            label: 'tâches',
            icon: Icons.check_circle_outline,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _Counter(
            value: byType['idea'] ?? 0,
            label: 'idées',
            icon: Icons.lightbulb_outline,
          ),
        ),
      ],
    );
  }
}

class _Counter extends StatelessWidget {
  const _Counter(
      {required this.value, required this.label, required this.icon});

  final int value;
  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
      decoration: cardDecoration(theme.colorScheme),
      child: Column(
        children: [
          Icon(icon, size: 18, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(height: 8),
          Text('$value', style: theme.textTheme.headlineSmall),
          Text(
            label,
            style: theme.textTheme.labelSmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title, this.trailing});

  final String title;
  final String? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          Text(
            title,
            style: theme.textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.w600),
          ),
          if (trailing != null) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: theme.colorScheme.tertiaryContainer,
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(
                trailing!,
                style: theme.textTheme.labelSmall
                    ?.copyWith(color: theme.colorScheme.onTertiaryContainer),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Text(
        message,
        style: theme.textTheme.bodyMedium
            ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
      ),
    );
  }
}

class _NeedsReviewLink extends ConsumerWidget {
  const _NeedsReviewLink({required this.count});

  final int count;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const Icon(Icons.help_outline),
      title: Text('$count élément${count > 1 ? 's' : ''} à confirmer'),
      subtitle: const Text("L'analyse a hésité sur ces éléments."),
      trailing: const Icon(Icons.chevron_right),
      onTap: () {
        ref.read(notesFilterProvider.notifier).state =
            const NotesFilter(status: EntryStatus.needsReview);
        context.push(Routes.notes);
      },
    );
  }
}

class _QuotaLine extends StatelessWidget {
  const _QuotaLine({required this.quota});

  final Map<String, int?> quota;

  @override
  Widget build(BuildContext context) {
    final limit = quota['limit'];
    final used = quota['used'] ?? 0;
    final theme = Theme.of(context);
    if (limit == null) {
      return Text(
        'Captures illimitées.',
        style: theme.textTheme.labelSmall
            ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
      );
    }
    final ratio = limit == 0 ? 1.0 : (used / limit).clamp(0.0, 1.0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '$used / $limit captures ce mois-ci',
          style: theme.textTheme.labelSmall
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: LinearProgressIndicator(value: ratio, minHeight: 4),
        ),
        if (used >= limit) ...[
          const SizedBox(height: 6),
          // Never phrased as a wall: over the limit, captures are still stored
          // and transcribed (ADR-026).
          Text(
            'Quota atteint : vos captures restent enregistrées et transcrites, '
            "l'analyse sera reprise plus tard.",
            style: theme.textTheme.labelSmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ],
      ],
    );
  }
}

class _PendingBanner extends ConsumerWidget {
  const _PendingBanner({required this.count});

  final int count;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.secondaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(Icons.cloud_upload_outlined, color: scheme.onSecondaryContainer),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '$count capture${count > 1 ? 's' : ''} en attente d’envoi.',
              style: TextStyle(color: scheme.onSecondaryContainer),
            ),
          ),
          TextButton(
            onPressed: () =>
                ref.read(captureControllerProvider.notifier).flushPending(),
            child: const Text('Réessayer'),
          ),
        ],
      ),
    );
  }
}

class _DashboardError extends StatelessWidget {
  const _DashboardError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 120),
        const Icon(Icons.cloud_off_outlined, size: 40),
        const SizedBox(height: 12),
        const Center(child: Text('Impossible de charger le tableau de bord.')),
        const SizedBox(height: 16),
        Center(
          child: TextButton(onPressed: onRetry, child: const Text('Réessayer')),
        ),
      ],
    );
  }
}
