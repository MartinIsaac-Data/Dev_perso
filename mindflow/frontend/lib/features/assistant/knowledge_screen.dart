/// What the product has learned: entities, recurring themes, and what the
/// assistant remembers about you.
///
/// Three panels, one screen, because they answer one question — "what does this
/// thing know?" — and splitting them across three destinations would make that
/// question take three navigations to answer.
///
/// The memory panel is the one with a product opinion behind it. Every remembered
/// fact is shown in full and can be deleted in one tap, because a memory store
/// the user cannot inspect is one they cannot correct, and an assistant
/// confidently wrong about them with no visible cause is worse than one that
/// remembers nothing at all.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/assistant_models.dart';
import '../../core/api/client.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import 'assistant_providers.dart';

class KnowledgeScreen extends ConsumerStatefulWidget {
  const KnowledgeScreen({super.key});

  @override
  ConsumerState<KnowledgeScreen> createState() => _KnowledgeScreenState();
}

class _KnowledgeScreenState extends ConsumerState<KnowledgeScreen>
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
        title: const Text('Connaissances'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'Entités'),
            Tab(text: 'Sujets récurrents'),
            Tab(text: 'Mémoire'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: const [_EntitiesPanel(), _ThemesPanel(), _MemoryPanel()],
      ),
    );
  }
}

class _EntitiesPanel extends ConsumerStatefulWidget {
  const _EntitiesPanel();

  @override
  ConsumerState<_EntitiesPanel> createState() => _EntitiesPanelState();
}

class _EntitiesPanelState extends ConsumerState<_EntitiesPanel> {
  EntityKind? _kind;

  @override
  Widget build(BuildContext context) {
    final entities = ref.watch(entitiesProvider(_kind));

    return Column(
      children: [
        SizedBox(
          height: 52,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: Space.lg),
            children: [
              _KindFilter(
                label: 'Tout',
                selected: _kind == null,
                onTap: () => setState(() => _kind = null),
              ),
              for (final kind in EntityKind.values)
                if (kind != EntityKind.unknown)
                  _KindFilter(
                    label: kind.label,
                    selected: _kind == kind,
                    onTap: () => setState(() => _kind = kind),
                  ),
            ],
          ),
        ),
        Expanded(
          child: entities.when(
            loading: () => const MfSkeletonList(),
            error: (error, _) => MfEmpty(
              icon: Icons.error_outline,
              title: 'Impossible de charger les entités',
              message: '$error',
            ),
            data: (rows) => rows.isEmpty
                ? const MfEmpty(
                    icon: Icons.hub_outlined,
                    title: 'Rien de détecté pour l\'instant',
                    // Explains *why* it is empty rather than just that it is:
                    // detection runs in the background, so an empty list right
                    // after a first capture is expected, not broken.
                    message: 'Les personnes, projets, décisions et risques '
                        'apparaissent ici à mesure que vos notes sont analysées.',
                  )
                : ListView.builder(
                    itemCount: rows.length,
                    itemExtent: 64,
                    itemBuilder: (context, index) =>
                        _EntityRow(entity: rows[index]),
                  ),
          ),
        ),
      ],
    );
  }
}

class _KindFilter extends StatelessWidget {
  const _KindFilter({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: Space.sm),
      child: Center(
        child: FilterChip(
          label: Text(label),
          selected: selected,
          onSelected: (_) => onTap(),
        ),
      ),
    );
  }
}

class _EntityRow extends StatelessWidget {
  const _EntityRow({required this.entity});

  final KnownEntity entity;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      title: Text(entity.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        entity.detail ?? entity.kind.label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: Text(
        '${entity.mentionCount}',
        style: theme.textTheme.labelMedium
            ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
      ),
    );
  }
}

class _ThemesPanel extends ConsumerWidget {
  const _ThemesPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themes = ref.watch(themesProvider);

    return themes.when(
      loading: () => const MfSkeletonList(),
      error: (error, _) => MfEmpty(
        icon: Icons.error_outline,
        title: 'Impossible de charger les sujets',
        message: '$error',
      ),
      data: (rows) {
        if (rows.isEmpty) {
          return const MfEmpty(
            icon: Icons.repeat,
            title: 'Pas encore de sujet récurrent',
            message: 'Un sujet apparaît ici dès qu\'il revient dans plusieurs '
                'notes. Comptés exactement, jamais estimés.',
          );
        }
        // The bar length is relative to the most-mentioned subject, so the
        // shape of the list is legible at a glance without any axis labels.
        final peak = rows.first.count;
        return ListView.builder(
          padding: const EdgeInsets.all(Space.lg),
          itemCount: rows.length,
          itemBuilder: (context, index) =>
              _ThemeRow(theme: rows[index], peak: peak),
        );
      },
    );
  }
}

class _ThemeRow extends StatelessWidget {
  const _ThemeRow({required this.theme, required this.peak});

  final RecurringTheme theme;
  final int peak;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(theme.name,
                    maxLines: 1, overflow: TextOverflow.ellipsis),
              ),
              const SizedBox(width: Space.sm),
              MfChip(label: theme.kind.label),
              const SizedBox(width: Space.sm),
              Text('${theme.count}', style: text.labelMedium),
            ],
          ),
          const SizedBox(height: Space.xs),
          MfProgressBar(value: peak == 0 ? 0 : theme.count / peak),
        ],
      ),
    );
  }
}

class _MemoryPanel extends ConsumerWidget {
  const _MemoryPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final memories = ref.watch(memoriesProvider);

    return memories.when(
      loading: () => const MfSkeletonList(),
      error: (error, _) => MfEmpty(
        icon: Icons.error_outline,
        title: 'Impossible de charger la mémoire',
        message: '$error',
      ),
      data: (rows) {
        if (rows.isEmpty) {
          return const MfEmpty(
            icon: Icons.psychology_outlined,
            title: 'L\'assistant ne retient rien pour l\'instant',
            message: 'Il ne retient que les faits durables : votre rôle, vos '
                'préférences, qui est qui. La plupart des conversations n\'en '
                'produisent aucun.',
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.all(Space.lg),
          itemCount: rows.length,
          itemBuilder: (context, index) => _MemoryRow(memory: rows[index]),
        );
      },
    );
  }
}

class _MemoryRow extends ConsumerWidget {
  const _MemoryRow({required this.memory});

  final Memory memory;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(memory.statement, style: theme.textTheme.bodyMedium),
                const SizedBox(height: Space.xs),
                Row(
                  children: [
                    MfChip(label: memory.label),
                    if (memory.isFading) ...[
                      const SizedBox(width: Space.sm),
                      // Shown rather than hidden: a fact confirmed months ago
                      // carries less weight in the assistant's answers, and
                      // saying so beats letting the user wonder why it seems
                      // half-remembered.
                      MfMeta(label: 'ancien', icon: Icons.schedule),
                    ],
                  ],
                ),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.close, size: 18),
            tooltip: 'Oublier définitivement',
            onPressed: () async {
              await ref.read(apiProvider).forgetMemory(memory.id);
              ref.invalidate(memoriesProvider);
            },
          ),
        ],
      ),
    );
  }
}
