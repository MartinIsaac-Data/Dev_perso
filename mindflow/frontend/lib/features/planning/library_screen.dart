/// The library: projects, tags and saved filters.
///
/// One screen with three tabs because they answer the same question — "how do I
/// organise my own material?" — and because the interesting operation is shared
/// between them: **merge**. Without a way to fold `#Finance` into `#finance`,
/// a tag list accumulates near-duplicates until nobody uses tags at all.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../core/api/errors.dart';
import '../../core/api/planning_models.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import 'planning_providers.dart';

class LibraryScreen extends ConsumerWidget {
  const LibraryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Bibliothèque'),
          bottom: const TabBar(
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            tabs: [
              Tab(text: 'Projets'),
              Tab(text: 'Tags'),
              Tab(text: 'Filtres'),
            ],
          ),
        ),
        body: const TabBarView(
          children: [_ProjectsTab(), _TagsTab(), _FiltersTab()],
        ),
      ),
    );
  }
}

class _ProjectsTab extends ConsumerWidget {
  const _ProjectsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projects = ref.watch(projectsProvider);

    return projects.when(
      loading: () => const MfSkeletonList(),
      error: (error, _) => MfEmpty(
        icon: Icons.folder_off_outlined,
        title: 'Projets indisponibles',
        message: error is ApiException ? error.userMessage : null,
      ),
      data: (data) => data.isEmpty
          ? const MfEmpty(
              icon: Icons.folder_outlined,
              title: 'Aucun projet',
              message: 'Un projet regroupe des notes et des tâches liées.',
            )
          : MfContentColumn(
              padding: EdgeInsets.zero,
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(vertical: Space.sm),
                itemCount: data.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, index) => _ProjectTile(
                  key: ValueKey(data[index].id),
                  project: data[index],
                ),
              ),
            ),
    );
  }
}

class _ProjectTile extends ConsumerWidget {
  const _ProjectTile({required this.project, super.key});

  final ProjectDetail project;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(
        horizontal: Space.lg,
        vertical: Space.xs,
      ),
      leading: Icon(
        Icons.folder_outlined,
        size: 18,
        color: _parseColor(project.color) ?? scheme.onSurfaceVariant,
      ),
      title: Text(project.name, style: theme.textTheme.bodyMedium),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (project.description != null)
            Text(
              project.description!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall,
            ),
          const SizedBox(height: Space.xs),
          Row(
            children: [
              Expanded(child: MfProgressBar(value: project.progress)),
              const SizedBox(width: Space.sm),
              Text(
                '${project.doneCount}/${project.totalCount}',
                style: theme.textTheme.labelSmall,
              ),
            ],
          ),
        ],
      ),
      trailing: IconButton(
        tooltip: project.pinned ? 'Détacher' : 'Épingler',
        icon: Icon(
          project.pinned ? Icons.push_pin : Icons.push_pin_outlined,
          size: 16,
        ),
        onPressed: () => ref
            .read(planningActionsProvider)
            .updateProject(project.id, pinned: !project.pinned),
      ),
      onTap: () => context.push('${Routes.search}?q=@${project.slug}'),
    );
  }
}

class _TagsTab extends ConsumerWidget {
  const _TagsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tags = ref.watch(tagsProvider);

    return tags.when(
      loading: () => const MfSkeletonList(),
      error: (error, _) => MfEmpty(
        icon: Icons.sell_outlined,
        title: 'Tags indisponibles',
        message: error is ApiException ? error.userMessage : null,
      ),
      data: (data) => data.isEmpty
          ? const MfEmpty(
              icon: Icons.sell_outlined,
              title: 'Aucun tag',
              message: "Les tags sont proposés par l'analyse de vos captures.",
            )
          : MfContentColumn(
              child: ListView(
                padding: const EdgeInsets.symmetric(vertical: Space.lg),
                children: [
                  const MfNotice(
                    icon: Icons.info_outline,
                    message:
                        'Renommer un tag vers un nom existant les fusionne.',
                  ),
                  const SizedBox(height: Space.lg),
                  Wrap(
                    spacing: Space.sm,
                    runSpacing: Space.sm,
                    children: [
                      for (final tag in data)
                        MfChip(
                          label: '${tag.label} · ${tag.usageCount}',
                          icon: tag.pinned ? Icons.push_pin : null,
                          color: _parseColor(tag.color),
                          onTap: () => _rename(context, ref, tag),
                        ),
                    ],
                  ),
                ],
              ),
            ),
    );
  }

  Future<void> _rename(BuildContext context, WidgetRef ref, Tag tag) async {
    final messenger = ScaffoldMessenger.of(context);
    final controller = TextEditingController(text: tag.label);

    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Renommer le tag'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Libellé'),
          onSubmitted: (value) => Navigator.of(context).pop(value),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop('__delete__'),
            child: const Text('Supprimer'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text),
            child: const Text('Renommer'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (result == null) return;

    try {
      if (result == '__delete__') {
        await ref.read(planningActionsProvider).deleteTag(tag.id);
      } else if (result.trim().isNotEmpty && result != tag.label) {
        await ref
            .read(planningActionsProvider)
            .renameTag(tag.id, result.trim());
      }
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }
}

class _FiltersTab extends ConsumerWidget {
  const _FiltersTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filters = ref.watch(savedFiltersProvider);

    return filters.when(
      loading: () => const MfSkeletonList(),
      error: (error, _) => MfEmpty(
        icon: Icons.bookmark_border,
        title: 'Filtres indisponibles',
        message: error is ApiException ? error.userMessage : null,
      ),
      data: (data) => data.isEmpty
          ? MfEmpty(
              icon: Icons.bookmark_border,
              title: 'Aucun filtre enregistré',
              message: 'Enregistrez une recherche pour la retrouver ici.',
              action: FilledButton(
                onPressed: () => context.go(Routes.search),
                child: const Text('Rechercher'),
              ),
            )
          : MfContentColumn(
              padding: EdgeInsets.zero,
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(vertical: Space.sm),
                itemCount: data.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, index) {
                  final filter = data[index];
                  return ListTile(
                    contentPadding:
                        const EdgeInsets.symmetric(horizontal: Space.lg),
                    leading: Icon(
                      filter.pinned ? Icons.push_pin : Icons.bookmark_outline,
                      size: 18,
                    ),
                    title: Text(
                      filter.name,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    subtitle: Text(
                      filter.query,
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                    trailing: IconButton(
                      tooltip: 'Supprimer',
                      icon: const Icon(Icons.delete_outline, size: 16),
                      onPressed: () => ref
                          .read(planningActionsProvider)
                          .deleteFilter(filter.id),
                    ),
                    onTap: () => context.go(
                        '${Routes.search}?q=${Uri.encodeComponent(filter.query)}'),
                  );
                },
              ),
            ),
    );
  }
}

Color? _parseColor(String? hex) {
  if (hex == null || hex.length != 7 || !hex.startsWith('#')) return null;
  final value = int.tryParse(hex.substring(1), radix: 16);
  return value == null ? null : Color(0xFF000000 | value);
}
