/// The list of everything MindFlow has extracted.
///
/// Filtering happens server-side. Fetching everything and filtering on the
/// device works for the first hundred entries and quietly stops working after
/// that; the API already supports the filters, so the client uses them.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../core/api/errors.dart';
import '../../core/api/models.dart';
import 'entry_tile.dart';
import 'notes_providers.dart';

class NotesScreen extends ConsumerStatefulWidget {
  const NotesScreen({super.key});

  @override
  ConsumerState<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends ConsumerState<NotesScreen> {
  final _search = TextEditingController();
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _search.text = ref.read(notesFilterProvider).search;
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  /// 350 ms: long enough that typing "réunion" is one request instead of seven,
  /// short enough that the list does not feel stuck.
  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      final filter = ref.read(notesFilterProvider);
      ref.read(notesFilterProvider.notifier).state =
          filter.copyWith(search: value.trim());
    });
  }

  @override
  Widget build(BuildContext context) {
    final filter = ref.watch(notesFilterProvider);
    final notes = ref.watch(notesProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Mes notes')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: TextField(
              key: const Key('notes_search'),
              controller: _search,
              onChanged: _onSearchChanged,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: 'Rechercher…',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: filter.search.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () {
                          _search.clear();
                          _onSearchChanged('');
                        },
                      ),
              ),
            ),
          ),
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              children: [
                _FilterChip(
                  label: 'Tout',
                  selected: filter.type == null && filter.status == null,
                  onSelected: () => ref
                      .read(notesFilterProvider.notifier)
                      .state = NotesFilter(search: filter.search),
                ),
                _FilterChip(
                  label: 'À vérifier',
                  selected: filter.status == EntryStatus.needsReview,
                  onSelected: () => ref
                          .read(notesFilterProvider.notifier)
                          .state =
                      filter.status == EntryStatus.needsReview
                          ? filter.copyWith(clearStatus: true)
                          : filter.copyWith(status: EntryStatus.needsReview),
                ),
                for (final type in const [
                  EntryType.task,
                  EntryType.idea,
                  EntryType.note,
                  EntryType.decision,
                  EntryType.question,
                ])
                  _FilterChip(
                    label: entryTypeLabel(type),
                    selected: filter.type == type,
                    onSelected: () =>
                        ref.read(notesFilterProvider.notifier).state =
                            filter.type == type
                                ? filter.copyWith(clearType: true)
                                : filter.copyWith(type: type),
                  ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: notes.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => _ListError(
                message: error is ApiException
                    ? error.userMessage
                    : 'Impossible de charger vos notes.',
                onRetry: () => ref.invalidate(notesProvider),
              ),
              data: (entries) => entries.isEmpty
                  ? const _EmptyList()
                  : RefreshIndicator(
                      onRefresh: () async {
                        ref.invalidate(notesProvider);
                        await ref.read(notesProvider.future);
                      },
                      child: ListView.separated(
                        padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
                        itemCount: entries.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, index) {
                          final entry = entries[index];
                          return Dismissible(
                            key: ValueKey(entry.id),
                            direction: DismissDirection.endToStart,
                            background: Container(
                              alignment: Alignment.centerRight,
                              padding: const EdgeInsets.only(right: 20),
                              color:
                                  Theme.of(context).colorScheme.errorContainer,
                              child: const Icon(Icons.delete_outline),
                            ),
                            confirmDismiss: (_) =>
                                _confirmDelete(context, entry),
                            onDismissed: (_) =>
                                ref.read(entryActionsProvider).delete(entry),
                            child: EntryTile(
                              entry: entry,
                              onTap: () => context.push(Routes.note(entry.id)),
                              onToggleDone: () async {
                                // Captured before the await: reading it after
                                // would be a use of `context` across an async
                                // gap, and the tile may be gone by then.
                                final messenger = ScaffoldMessenger.of(context);
                                try {
                                  await ref
                                      .read(entryActionsProvider)
                                      .toggleDone(entry);
                                } on ApiException catch (error) {
                                  messenger.showSnackBar(
                                    SnackBar(content: Text(error.userMessage)),
                                  );
                                }
                              },
                            ),
                          );
                        },
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Future<bool> _confirmDelete(BuildContext context, Entry entry) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Supprimer cet élément ?'),
        content: Text(
          entry.captureId == null
              ? 'Cette action est définitive.'
              : "L'enregistrement audio d'origine, lui, est conservé.",
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onSelected,
  });

  final String label;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: FilterChip(
        label: Text(label),
        selected: selected,
        onSelected: (_) => onSelected(),
      ),
    );
  }
}

class _EmptyList extends StatelessWidget {
  const _EmptyList();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.mic_none, size: 44, color: theme.colorScheme.outline),
            const SizedBox(height: 16),
            Text('Rien ici pour le moment.',
                style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              'Appuyez sur Capturer et dites ce que vous avez en tête.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

class _ListError extends StatelessWidget {
  const _ListError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          TextButton(onPressed: onRetry, child: const Text('Réessayer')),
        ],
      ),
    );
  }
}
