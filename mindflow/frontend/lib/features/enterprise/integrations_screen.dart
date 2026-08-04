/// Connected services, and the conflicts they produce.
///
/// Three things on this screen are deliberate and easy to get wrong.
///
/// **`expired` and `error` are not the same state, so they do not get the same
/// button.** A revoked grant will never recover on a retry; offering « Réessayer »
/// there sends somebody round a loop that cannot terminate. Only « Reconnecter »
/// is shown.
///
/// **Obsidian has no « Synchroniser » button at all**, and the screen says why
/// rather than leaving a greyed control to be puzzled over: it is a folder on a
/// disk, and the server has no access to it.
///
/// **A conflict is presented as a choice, never resolved on the user's behalf.**
/// Both sides changed, which means both mattered to somebody; picking one
/// silently is how the version they cared about disappears.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/enterprise_models.dart';
import '../../core/api/errors.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import 'enterprise_providers.dart';
import 'enterprise_ui.dart';

class IntegrationsScreen extends ConsumerStatefulWidget {
  const IntegrationsScreen({super.key});

  @override
  ConsumerState<IntegrationsScreen> createState() => _IntegrationsScreenState();
}

class _IntegrationsScreenState extends ConsumerState<IntegrationsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 2, vsync: this);

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final conflicts = ref.watch(conflictsProvider);
    final pending = conflicts.maybeWhen(
      data: (items) => items.length,
      orElse: () => 0,
    );

    return Scaffold(
      appBar: AppBar(
        title: const Text('Intégrations'),
        bottom: TabBar(
          controller: _tabs,
          tabs: [
            const Tab(text: 'Services'),
            Tab(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('Conflits'),
                  if (pending > 0) ...[
                    const SizedBox(width: Space.sm),
                    Badge(label: Text('$pending')),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: const [_ConnectionsPanel(), _ConflictsPanel()],
      ),
    );
  }
}

class _ConnectionsPanel extends ConsumerWidget {
  const _ConnectionsPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final connections = ref.watch(integrationsProvider);

    return connections.when(
      loading: () => const MfSkeletonList(rows: 4),
      error: (error, _) => MfEmpty(
        icon: Icons.error_outline,
        title: 'Impossible de charger les intégrations',
        message: describeError(error),
      ),
      data: (items) {
        final connected = {for (final item in items) item.provider: item};
        return ListView(
          padding: const EdgeInsets.all(Space.lg),
          children: [
            const MfNotice(
              icon: Icons.info_outline,
              message: 'Par défaut, MindFlow lit et n\'écrit pas. Écrire dans '
                  'votre agenda est un choix explicite.',
            ),
            for (final provider in SyncProvider.values)
              if (provider != SyncProvider.unknown)
                _ProviderCard(
                  provider: provider,
                  connection: connected[provider],
                ),
          ],
        );
      },
    );
  }
}

class _ProviderCard extends ConsumerWidget {
  const _ProviderCard({required this.provider, this.connection});

  final SyncProvider provider;
  final Connection? connection;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final live = connection;

    return Container(
      margin: const EdgeInsets.only(top: Space.md),
      padding: const EdgeInsets.all(Space.lg),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: Radii.mdAll,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(provider.label, style: theme.textTheme.titleSmall),
              ),
              if (live != null) MfChip(label: live.status.label),
            ],
          ),
          const SizedBox(height: Space.xs),
          Text(provider.summary, style: theme.textTheme.bodySmall),
          if (provider == SyncProvider.obsidian) ...[
            const SizedBox(height: Space.sm),
            Text(
              'Obsidian est un dossier sur votre disque, pas un service : la '
              'synchronisation se fait dans l\'application et le serveur n\'y '
              'a aucun accès.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ],
          if (live != null && live.status.needsAttention) ...[
            const SizedBox(height: Space.md),
            MfNotice(
              icon: Icons.warning_amber_outlined,
              tone: MfNoticeTone.warning,
              message: live.status.remedy,
            ),
          ],
          const SizedBox(height: Space.md),
          Row(
            children: [
              if (live == null)
                FilledButton.tonal(
                  onPressed: () => _connect(context, ref),
                  child: const Text('Connecter'),
                )
              else ...[
                // No "sync now" for a non-server-side connector — the button
                // would call an endpoint that deliberately does no I/O.
                if (live.serverSide)
                  OutlinedButton(
                    onPressed: () => _sync(context, ref, live),
                    child: const Text('Synchroniser'),
                  ),
                const SizedBox(width: Space.sm),
                TextButton(
                  onPressed: () => _disconnect(context, ref, live),
                  child: const Text('Déconnecter'),
                ),
              ],
              const Spacer(),
              if (live?.lastSyncAt != null)
                Text(
                  'Dernière sync ${formatRelativePast(live!.lastSyncAt!)}',
                  style: theme.textTheme.bodySmall,
                ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _connect(BuildContext context, WidgetRef ref) async {
    // OAuth is not wired: there is no authorisation server to redirect to in
    // this build. Asking for the token directly is honest about that rather
    // than showing a "Se connecter avec Google" button that goes nowhere.
    final token = await promptForText(
      context,
      title: 'Connecter ${provider.label}',
      hint: 'Jeton d\'accès',
      confirm: 'Connecter',
      helper: 'Le jeton est chiffré avant d\'atteindre le disque et n\'est '
          'jamais réaffiché.',
    );
    if (token == null || token.trim().isEmpty) return;
    try {
      await ref
          .read(enterpriseActionsProvider)
          .connect(provider: provider, accessToken: token.trim());
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }

  Future<void> _sync(
      BuildContext context, WidgetRef ref, Connection connection) async {
    try {
      final report =
          await ref.read(enterpriseActionsProvider).syncNow(connection.id);
      if (!context.mounted) return;
      // A provider outage comes back as a 200 with `failed`. Reporting it as
      // an error snack would be right; reporting it as a crash would not.
      showMessage(
        context,
        report.failed
            ? 'Synchronisation impossible : ${report.reason}'
            : '${report.changed} élément(s) mis à jour, '
                '${report.conflicts} conflit(s)',
      );
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }

  Future<void> _disconnect(
      BuildContext context, WidgetRef ref, Connection connection) async {
    final confirmed = await confirmDestructive(
      context,
      title: 'Déconnecter ${provider.label} ?',
      message: 'Le jeton est supprimé. Les notes déjà synchronisées restent '
          'en place des deux côtés.',
      confirm: 'Déconnecter',
    );
    if (!confirmed) return;
    try {
      await ref.read(enterpriseActionsProvider).disconnect(connection.id);
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }
}

class _ConflictsPanel extends ConsumerWidget {
  const _ConflictsPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final conflicts = ref.watch(conflictsProvider);

    return conflicts.when(
      loading: () => const MfSkeletonList(rows: 3),
      error: (error, _) => MfEmpty(
        icon: Icons.error_outline,
        title: 'Impossible de charger les conflits',
        message: describeError(error),
      ),
      data: (items) => items.isEmpty
          ? const MfEmpty(
              icon: Icons.check_circle_outline,
              title: 'Aucun conflit',
              message: 'Quand un élément change des deux côtés en même temps, '
                  'MindFlow ne tranche pas tout seul : il vous le montre ici.',
            )
          : ListView.builder(
              padding: const EdgeInsets.all(Space.lg),
              itemCount: items.length,
              itemBuilder: (context, index) =>
                  _ConflictCard(conflict: items[index]),
            ),
    );
  }
}

class _ConflictCard extends ConsumerWidget {
  const _ConflictCard({required this.conflict});

  final SyncConflict conflict;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: Space.md),
      padding: const EdgeInsets.all(Space.lg),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: Radii.mdAll,
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(conflict.provider.label, style: theme.textTheme.titleSmall),
          const SizedBox(height: Space.xs),
          Text(
            conflict.detectedAt == null
                ? 'Modifié des deux côtés depuis la dernière synchronisation.'
                : 'Modifié des deux côtés · '
                    '${formatRelativePast(conflict.detectedAt!)}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: Space.md),
          // Wrap, not Row: the two labels are long by design — « Garder » is
          // clearer than an icon here — and on a phone they do not fit side by
          // side. A Row would clip one of the two choices, which on this card
          // means offering a conflict with only one way out.
          Wrap(
            spacing: Space.sm,
            runSpacing: Space.sm,
            children: [
              OutlinedButton(
                onPressed: () => _resolve(context, ref, keepLocal: true),
                child: const Text('Garder la version MindFlow'),
              ),
              OutlinedButton(
                onPressed: () => _resolve(context, ref, keepLocal: false),
                child: const Text('Garder la version distante'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _resolve(BuildContext context, WidgetRef ref,
      {required bool keepLocal}) async {
    try {
      await ref
          .read(enterpriseActionsProvider)
          .resolveConflict(conflict.id, keepLocal: keepLocal);
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }
}
