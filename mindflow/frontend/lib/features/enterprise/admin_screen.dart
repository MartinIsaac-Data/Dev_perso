/// Administration: what the account contains, what happened, and what is about
/// to break.
///
/// The health panel is the reason this screen exists rather than being three
/// numbers on the dashboard. `audit_partition_gap` is the only signal in the
/// product that *predicts* an outage instead of reporting one — next month has
/// no partition, so every audit write will fail on the 1st — and it has no other
/// symptom until then. Anything that behaves like that has to be shown
/// somewhere a person looks.
///
/// What this screen deliberately does not do: show anybody's notes. It counts
/// rows; it displays none. An account administrator cannot read a colleague's
/// private notes, and that limit is enforced by a PostgreSQL policy rather than
/// by this screen choosing not to ask.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/enterprise_models.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import 'enterprise_providers.dart';
import 'enterprise_ui.dart';

class AdminScreen extends ConsumerStatefulWidget {
  const AdminScreen({super.key});

  @override
  ConsumerState<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends ConsumerState<AdminScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 3, vsync: this);

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Administration'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'Vue d\'ensemble'),
            Tab(text: 'Journal d\'audit'),
            Tab(text: 'Usage'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: const [_OverviewPanel(), _AuditPanel(), _UsagePanel()],
      ),
    );
  }
}

class _OverviewPanel extends ConsumerWidget {
  const _OverviewPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overview = ref.watch(overviewProvider);
    final health = ref.watch(healthProvider);

    return ListView(
      padding: const EdgeInsets.all(Space.lg),
      children: [
        health.when(
          loading: () => const MfSkeleton(height: 40),
          error: (error, _) => MfNotice(
            icon: Icons.error_outline,
            tone: MfNoticeTone.danger,
            message: describeError(error),
          ),
          data: _HealthNotices.new,
        ),
        overview.when(
          loading: () => const Padding(
            padding: EdgeInsets.only(top: Space.xl),
            child: MfSkeleton(height: 160),
          ),
          error: (error, _) => Padding(
            padding: const EdgeInsets.only(top: Space.xl),
            child: MfNotice(
              icon: Icons.lock_outline,
              tone: MfNoticeTone.warning,
              message: describeError(error),
            ),
          ),
          data: (data) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const MfSectionHeader(title: 'Compte'),
              _StatGrid(entries: {
                'Membres': data.members,
                'Espaces': data.workspaces,
                'Notes': data.entries,
                'Captures': data.captures,
                'Commentaires': data.comments,
                'Liens actifs': data.activeShareLinks,
              }),
              const MfSectionHeader(title: 'Intégrations'),
              _StatGrid(entries: {
                'Connectées': data.connectedIntegrations,
                'À reconnecter': data.integrationsNeedingAttention,
              }),
              const MfSectionHeader(title: 'Index sémantique'),
              _StatGrid(entries: {
                'Indexé': data.indexedChunks,
                'En attente': data.pendingChunks,
              }),
              if (data.pendingChunks > 0)
                const Padding(
                  padding: EdgeInsets.only(top: Space.md),
                  child: MfNotice(
                    icon: Icons.hourglass_empty,
                    message: 'Une recherche sémantique sur un corpus en cours '
                        'd\'indexation ressemble à une recherche correcte. '
                        'Ce chiffre est la seule façon de les distinguer.',
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The two operational warnings, in the order somebody should act on them.
class _HealthNotices extends StatelessWidget {
  const _HealthNotices(this.health);

  final OperationalHealth health;

  @override
  Widget build(BuildContext context) {
    if (health.healthy) {
      return const MfNotice(
        icon: Icons.check_circle_outline,
        message: 'Rien à signaler.',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (health.auditPartitionGap)
          const Padding(
            padding: EdgeInsets.only(bottom: Space.sm),
            child: MfNotice(
              icon: Icons.event_busy,
              tone: MfNoticeTone.danger,
              message: 'Le mois prochain n\'a pas de partition d\'audit. '
                  'À partir du 1er, chaque écriture du journal échouera.',
            ),
          ),
        if (health.failingIntegrations.isNotEmpty)
          MfNotice(
            icon: Icons.sync_problem,
            tone: MfNoticeTone.warning,
            message: '${health.failingIntegrations.length} intégration(s) à '
                'reconnecter : ${health.failingIntegrations.join(', ')}',
          ),
      ],
    );
  }
}

class _StatGrid extends StatelessWidget {
  const _StatGrid({required this.entries});

  final Map<String, int> entries;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Wrap(
      spacing: Space.md,
      runSpacing: Space.md,
      children: [
        for (final entry in entries.entries)
          Container(
            width: 148,
            padding: const EdgeInsets.all(Space.md),
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerLow,
              borderRadius: Radii.mdAll,
              border: Border.all(color: theme.colorScheme.outlineVariant),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${entry.value}', style: theme.textTheme.headlineSmall),
                Text(entry.key, style: theme.textTheme.bodySmall),
              ],
            ),
          ),
      ],
    );
  }
}

class _AuditPanel extends ConsumerWidget {
  const _AuditPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final audit = ref.watch(auditProvider);

    return audit.when(
      loading: () => const MfSkeletonList(rows: 6),
      error: (error, _) => MfEmpty(
        icon: Icons.lock_outline,
        title: 'Journal indisponible',
        message: describeError(error),
      ),
      data: (entries) => entries.isEmpty
          ? const MfEmpty(
              icon: Icons.receipt_long_outlined,
              title: 'Rien sur les trente derniers jours',
              message: 'Le journal consigne les changements de droits, de '
                  'partage et de connexion — pas les consultations.',
            )
          : ListView.builder(
              padding: const EdgeInsets.symmetric(vertical: Space.md),
              itemCount: entries.length,
              itemBuilder: (context, index) {
                final entry = entries[index];
                return ListTile(
                  dense: true,
                  leading: const Icon(Icons.chevron_right, size: 16),
                  title: Text(entry.label),
                  subtitle: Text(
                    entry.occurredAt == null
                        ? entry.actorType
                        : '${entry.actorType} · '
                            '${formatTimestamp(entry.occurredAt!)}',
                  ),
                );
              },
            ),
    );
  }
}

class _UsagePanel extends ConsumerWidget {
  const _UsagePanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final usage = ref.watch(usageProvider);

    return usage.when(
      loading: () => const MfSkeletonList(rows: 6),
      error: (error, _) => MfEmpty(
        icon: Icons.lock_outline,
        title: 'Usage indisponible',
        message: describeError(error),
      ),
      data: (points) {
        if (points.isEmpty) {
          return const MfEmpty(
            icon: Icons.bar_chart_outlined,
            title: 'Aucune activité',
          );
        }
        final peak = points
            .map((point) => point.total)
            .fold<int>(1, (a, b) => a > b ? a : b);
        return ListView.builder(
          padding: const EdgeInsets.all(Space.lg),
          itemCount: points.length,
          itemBuilder: (context, index) {
            final point = points[index];
            return Padding(
              padding: const EdgeInsets.only(bottom: Space.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(child: Text(formatDay(point.day))),
                      Text('${point.total}'),
                    ],
                  ),
                  const SizedBox(height: Space.xs),
                  MfProgressBar(value: point.total / peak),
                ],
              ),
            );
          },
        );
      },
    );
  }
}
