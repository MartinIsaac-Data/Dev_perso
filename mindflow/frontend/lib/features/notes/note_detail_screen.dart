/// One entry, in full.
///
/// Two things this screen is careful about:
///
/// * **Provenance.** Every extracted entry links back to the recording it came
///   from. A user who doubts a task must be able to hear what they actually
///   said in one tap — that link is the difference between a tool people trust
///   and one they double-check elsewhere.
///
/// * **Correction is cheap.** Editing the title marks the entry as
///   human-corrected server-side (ADR-027), which makes it immune to being
///   overwritten by a later reprocessing run.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../core/api/errors.dart';
import '../../core/api/models.dart';
import '../../core/ui/formatting.dart';
import 'notes_providers.dart';

class NoteDetailScreen extends ConsumerWidget {
  const NoteDetailScreen({required this.entryId, super.key});

  final String entryId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final entry = ref.watch(entryProvider(entryId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Détail'),
        actions: [
          entry.maybeWhen(
            data: (value) => IconButton(
              tooltip: 'Supprimer',
              icon: const Icon(Icons.delete_outline),
              onPressed: () => _delete(context, ref, value),
            ),
            orElse: () => const SizedBox.shrink(),
          ),
        ],
      ),
      body: entry.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Text(
            error is ApiException ? error.userMessage : 'Introuvable.',
            textAlign: TextAlign.center,
          ),
        ),
        data: (value) => _Detail(entry: value),
      ),
    );
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, Entry entry) async {
    final navigator = Navigator.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Supprimer cet élément ?'),
        content: const Text(
          "L'enregistrement audio d'origine est conservé.",
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
    if (confirmed ?? false) {
      await ref.read(entryActionsProvider).delete(entry);
      navigator.pop();
    }
  }
}

class _Detail extends ConsumerStatefulWidget {
  const _Detail({required this.entry});

  final Entry entry;

  @override
  ConsumerState<_Detail> createState() => _DetailState();
}

class _DetailState extends ConsumerState<_Detail> {
  late final TextEditingController _title =
      TextEditingController(text: widget.entry.title);
  late final TextEditingController _body =
      TextEditingController(text: widget.entry.body ?? '');
  bool _editing = false;
  bool _saving = false;

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _saving = true);
    try {
      await ref.read(entryActionsProvider).edit(
            widget.entry,
            title: _title.text.trim(),
            body: _body.text.trim().isEmpty ? null : _body.text.trim(),
          );
      if (mounted) setState(() => _editing = false);
    } on ApiException catch (error) {
      // A version conflict is the interesting case: someone (or a reprocessing
      // run) changed the entry since it was loaded. Reload rather than
      // overwrite — the user's words are not more authoritative than their own
      // later words.
      if (error.isConflict) {
        ref.invalidate(entryProvider(widget.entry.id));
      }
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final entry = widget.entry;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final task = entry.task;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        Row(
          children: [
            Icon(entryIcon(entry.type),
                size: 18, color: entryColor(scheme, entry.type)),
            const SizedBox(width: 8),
            Text(
              entryTypeLabel(entry.type),
              style: theme.textTheme.labelLarge
                  ?.copyWith(color: entryColor(scheme, entry.type)),
            ),
            const Spacer(),
            if (entry.editedByUserAt != null)
              Tooltip(
                message:
                    'Corrigé par vous — ne sera pas réécrit par une nouvelle analyse.',
                child: Icon(Icons.edit_note,
                    size: 18, color: scheme.onSurfaceVariant),
              ),
          ],
        ),
        const SizedBox(height: 12),
        if (_editing) ...[
          TextField(
            key: const Key('detail_title'),
            controller: _title,
            maxLines: null,
            decoration: const InputDecoration(labelText: 'Titre'),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('detail_body'),
            controller: _body,
            maxLines: 6,
            decoration: const InputDecoration(labelText: 'Détail'),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _saving
                      ? null
                      : () => setState(() {
                            _title.text = entry.title;
                            _body.text = entry.body ?? '';
                            _editing = false;
                          }),
                  child: const Text('Annuler'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  key: const Key('detail_save'),
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Enregistrer'),
                ),
              ),
            ],
          ),
        ] else ...[
          Text(entry.title, style: theme.textTheme.headlineSmall),
          if ((entry.body ?? '').isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(entry.body!, style: theme.textTheme.bodyLarge),
          ],
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                key: const Key('detail_edit'),
                onPressed: () => setState(() => _editing = true),
                icon: const Icon(Icons.edit_outlined, size: 18),
                label: const Text('Modifier'),
              ),
              if (entry.type == EntryType.task)
                FilledButton.tonalIcon(
                  onPressed: () async {
                    final messenger = ScaffoldMessenger.of(context);
                    try {
                      await ref.read(entryActionsProvider).toggleDone(entry);
                    } on ApiException catch (error) {
                      messenger.showSnackBar(
                        SnackBar(content: Text(error.userMessage)),
                      );
                    }
                  },
                  icon: Icon(
                    entry.status == EntryStatus.done
                        ? Icons.undo
                        : Icons.check_circle_outline,
                    size: 18,
                  ),
                  label: Text(
                    entry.status == EntryStatus.done
                        ? 'Rouvrir'
                        : 'Marquer comme fait',
                  ),
                ),
            ],
          ),
        ],
        const SizedBox(height: 24),
        if (task != null && task.dueAt != null)
          _Fact(
            icon: Icons.schedule,
            label: 'Échéance',
            value: formatDue(task.dueAt, precision: task.duePrecision),
            // The raw wording is kept alongside the resolved date so a wrong
            // interpretation is visible instead of silent (ADR-020).
            hint: task.dueRawExpression == null
                ? null
                : '« ${task.dueRawExpression} »',
          ),
        if (entry.tags.isNotEmpty)
          _Fact(
            icon: Icons.sell_outlined,
            label: 'Tags',
            value: entry.tags.map((tag) => '#$tag').join('  '),
          ),
        _Fact(
          icon: Icons.event_outlined,
          label: 'Capturé',
          value: formatTimestamp(entry.occurredAt),
        ),
        if (entry.confidence != null)
          _Fact(
            icon: Icons.insights_outlined,
            label: 'Confiance de l’extraction',
            value: '${(entry.confidence! * 100).round()} %',
            hint: entry.needsReview
                ? "L'analyse a hésité : vérifiez ce que vous aviez dit."
                : null,
          ),
        if (entry.captureId != null) ...[
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: () => context.push(Routes.capture(entry.captureId!)),
            icon: const Icon(Icons.graphic_eq, size: 18),
            label: const Text("Écouter l'enregistrement d'origine"),
          ),
        ],
      ],
    );
  }
}

class _Fact extends StatelessWidget {
  const _Fact({
    required this.icon,
    required this.label,
    required this.value,
    this.hint,
  });

  final IconData icon;
  final String label;
  final String value;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: theme.textTheme.labelSmall
                      ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
                Text(value, style: theme.textTheme.bodyMedium),
                if (hint != null)
                  Text(
                    hint!,
                    style: theme.textTheme.labelSmall
                        ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
