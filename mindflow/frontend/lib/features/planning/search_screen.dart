/// Full-text search.
///
/// One box, one grammar. Free text and filters mix: `réunion DAF is:task
/// p:high #finance due:semaine`. The parsed query comes back from the server and
/// is rendered as chips, including the tokens it *could not* understand — a
/// search box that silently drops `p:hgih` and returns everything teaches the
/// user nothing.
///
/// Saved filters live here too, because the moment a query is worth typing twice
/// it is worth naming.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../core/api/errors.dart';
import '../../core/api/planning_models.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import 'entry_row.dart';
import 'planning_providers.dart';

class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key, this.initialQuery});

  final String? initialQuery;

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  late final TextEditingController _controller;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(
      text: widget.initialQuery ?? ref.read(searchQueryProvider),
    );
    if (widget.initialQuery != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(searchQueryProvider.notifier).state = widget.initialQuery!;
      });
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    _debounce?.cancel();
    // Longer than the palette's: full text runs a heavier query, and firing it
    // on every keystroke would queue requests the user has already superseded.
    _debounce = Timer(Freshness.searchDebounce, () {
      ref.read(searchQueryProvider.notifier).state = value;
    });
  }

  void _apply(String query) {
    _controller.text = query;
    _controller.selection = TextSelection.collapsed(offset: query.length);
    ref.read(searchQueryProvider.notifier).state = query;
  }

  @override
  Widget build(BuildContext context) {
    final results = ref.watch(searchResultsProvider);
    final filters = ref.watch(savedFiltersProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Recherche')),
      body: Column(
        children: [
          MfContentColumn(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: Space.sm),
                TextField(
                  key: const Key('search_input'),
                  controller: _controller,
                  onChanged: _onChanged,
                  autofocus: widget.initialQuery == null,
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: 'réunion  is:task  p:high  #finance  due:semaine',
                    prefixIcon: const Icon(Icons.search, size: 18),
                    suffixIcon: _controller.text.isEmpty
                        ? null
                        : IconButton(
                            icon: const Icon(Icons.close, size: 16),
                            onPressed: () => _apply(''),
                          ),
                  ),
                ),
                const SizedBox(height: Space.sm),
                filters.maybeWhen(
                  data: (saved) => saved.isEmpty
                      ? const SizedBox.shrink()
                      : _SavedFilterBar(filters: saved, onApply: _apply),
                  orElse: () => const SizedBox.shrink(),
                ),
              ],
            ),
          ),
          const Divider(height: Space.lg),
          Expanded(
            child: results.when(
              loading: () => const MfSkeletonList(),
              error: (error, _) => MfEmpty(
                icon: Icons.search_off,
                title: 'Recherche indisponible',
                message: error is ApiException ? error.userMessage : null,
              ),
              data: (data) => data == null
                  ? const _SearchHelp()
                  : _Results(
                      results: data, onSave: () => _saveCurrent(context)),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _saveCurrent(BuildContext context) async {
    final query = ref.read(searchQueryProvider);
    if (query.trim().isEmpty) return;

    final messenger = ScaffoldMessenger.of(context);
    final name = await showDialog<String>(
      context: context,
      builder: (context) => _NameFilterDialog(query: query),
    );
    if (name == null || name.trim().isEmpty) return;

    try {
      await ref
          .read(planningActionsProvider)
          .saveFilter(name: name, query: query);
      messenger.showSnackBar(
          SnackBar(content: Text('Filtre « $name » enregistré.')));
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }
}

class _SavedFilterBar extends ConsumerWidget {
  const _SavedFilterBar({required this.filters, required this.onApply});

  final List<SavedFilter> filters;
  final ValueChanged<String> onApply;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SizedBox(
      height: 30,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: filters.length,
        separatorBuilder: (_, __) => const SizedBox(width: Space.sm),
        itemBuilder: (context, index) {
          final filter = filters[index];
          return GestureDetector(
            onLongPress: () =>
                ref.read(planningActionsProvider).deleteFilter(filter.id),
            child: MfChip(
              label: filter.name,
              icon: filter.pinned ? Icons.push_pin : Icons.bookmark_outline,
              onTap: () => onApply(filter.query),
            ),
          );
        },
      ),
    );
  }
}

class _Results extends ConsumerWidget {
  const _Results({required this.results, required this.onSave});

  final SearchResults results;
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    if (results.isEmpty) {
      return MfEmpty(
        icon: Icons.search_off,
        title: 'Aucun résultat',
        message: results.query.ignored.isEmpty
            ? 'Essayez d’élargir la recherche.'
            : 'Filtres ignorés : ${results.query.ignored.join(', ')}',
      );
    }

    return Column(
      children: [
        MfContentColumn(
          child: Row(
            children: [
              Text(
                '${results.total} résultat${results.total > 1 ? 's' : ''} · ${results.tookMs} ms',
                style: theme.textTheme.labelSmall,
              ),
              const Spacer(),
              TextButton.icon(
                onPressed: onSave,
                icon: const Icon(Icons.bookmark_add_outlined, size: 15),
                label: const Text('Enregistrer'),
              ),
            ],
          ),
        ),
        if (results.query.ignored.isNotEmpty)
          MfContentColumn(
            child: Padding(
              padding: const EdgeInsets.only(bottom: Space.sm),
              child: MfNotice(
                icon: Icons.info_outline,
                tone: MfNoticeTone.warning,
                message: 'Ignoré : ${results.query.ignored.join(', ')}',
              ),
            ),
          ),
        Expanded(
          child: MfContentColumn(
            padding: EdgeInsets.zero,
            child: ListView.builder(
              itemCount: results.hits.length,
              itemBuilder: (context, index) {
                final hit = results.hits[index];
                return _Hit(
                  key: ValueKey(hit.entry.id),
                  hit: hit,
                  onTap: () => context.push(Routes.note(hit.entry.id)),
                );
              },
            ),
          ),
        ),
      ],
    );
  }
}

class _Hit extends StatelessWidget {
  const _Hit({required this.hit, required this.onTap, super.key});

  final SearchHit hit;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        EntryRow(entry: hit.entry, onTap: onTap, showDay: true),
        if (hit.snippet != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(
                Space.xxl + Space.sm, 0, Space.md, Space.sm),
            child: _Snippet(
                snippet: hit.snippet!, style: theme.textTheme.bodySmall),
          ),
      ],
    );
  }
}

/// Renders the server's `«…»` markers as bold spans.
///
/// The highlight is produced by PostgreSQL's `ts_headline`, which knows exactly
/// which lexemes matched. Re-tokenising on the client would sometimes disagree
/// with the ranking — highlighting a word that did not contribute to the score.
class _Snippet extends StatelessWidget {
  const _Snippet({required this.snippet, this.style});

  final String snippet;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final spans = <TextSpan>[];
    var rest = snippet;

    while (true) {
      final open = rest.indexOf('«');
      if (open < 0) break;
      final close = rest.indexOf('»', open);
      if (close < 0) break;

      if (open > 0) spans.add(TextSpan(text: rest.substring(0, open)));
      spans.add(TextSpan(
        text: rest.substring(open + 1, close),
        style: const TextStyle(fontWeight: FontWeight.w700),
      ));
      rest = rest.substring(close + 1);
    }
    if (rest.isNotEmpty) spans.add(TextSpan(text: rest));

    return Text.rich(
      TextSpan(children: spans, style: style),
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
    );
  }
}

class _SearchHelp extends StatelessWidget {
  const _SearchHelp();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    const examples = <(String, String)>[
      ('is:task', 'seulement les tâches'),
      ('p:urgent', 'priorité urgente'),
      ('#finance', 'portant ce tag'),
      ('@refonte', 'dans ce projet'),
      ('due:semaine', 'échéance cette semaine'),
      ('is:overdue', 'en retard'),
      ('"appel du lundi"', 'expression exacte'),
    ];

    return MfContentColumn(
      child: ListView(
        children: [
          const SizedBox(height: Space.xl),
          Text('Filtres disponibles', style: theme.textTheme.titleSmall),
          const SizedBox(height: Space.md),
          for (final (token, meaning) in examples)
            Padding(
              padding: const EdgeInsets.only(bottom: Space.sm),
              child: Row(
                children: [
                  SizedBox(width: 150, child: MfChip(label: token)),
                  const SizedBox(width: Space.md),
                  Text(meaning, style: theme.textTheme.bodySmall),
                ],
              ),
            ),
          const SizedBox(height: Space.lg),
          Text(
            'Le texte libre et les filtres se combinent. '
            'Un mot que MindFlow ne reconnaît pas est traité comme du texte, '
            'jamais rejeté.',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _NameFilterDialog extends StatefulWidget {
  const _NameFilterDialog({required this.query});

  final String query;

  @override
  State<_NameFilterDialog> createState() => _NameFilterDialogState();
}

class _NameFilterDialogState extends State<_NameFilterDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Enregistrer ce filtre'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _controller,
            autofocus: true,
            decoration: const InputDecoration(labelText: 'Nom'),
            onSubmitted: (value) => Navigator.of(context).pop(value),
          ),
          const SizedBox(height: Space.md),
          MfChip(label: widget.query),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Annuler'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_controller.text),
          child: const Text('Enregistrer'),
        ),
      ],
    );
  }
}
