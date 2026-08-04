/// The discussion under a note.
///
/// One behaviour here is the whole reason the panel is not a plain list.
///
/// When a comment mentions somebody who cannot read the note, the server
/// resolves nothing and returns the handle in `unresolved_mentions`. The panel
/// says so — « Paul n'a pas accès à cette note » — because the alternative is
/// that the author believes Paul was notified and waits for an answer that will
/// never come. A silent failure is the expensive kind.
///
/// Editing is restricted to one's own comment and it is not the client that
/// enforces it — the server refuses, and this only avoids offering a button
/// that always fails. An administrator may delete a comment and never rewrite
/// it: a thread somebody else can edit is not a record of anything.
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

class CommentsPanel extends ConsumerStatefulWidget {
  const CommentsPanel({required this.entryId, super.key});

  final String entryId;

  @override
  ConsumerState<CommentsPanel> createState() => _CommentsPanelState();
}

class _CommentsPanelState extends ConsumerState<CommentsPanel> {
  final _controller = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final body = _controller.text.trim();
    if (body.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      final comment = await ref
          .read(enterpriseActionsProvider)
          .comment(widget.entryId, body);
      _controller.clear();
      // Reported once, at the moment it matters. Leaving it only in the list
      // would let it scroll away unread.
      if (comment.unresolvedMentions.isNotEmpty && mounted) {
        showMessage(context, _unresolvedMessage(comment.unresolvedMentions));
      }
    } on ApiException catch (error) {
      if (mounted) showErrorSnack(context, error);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final comments = ref.watch(commentsProvider(widget.entryId));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const MfSectionHeader(title: 'Discussion'),
        comments.when(
          loading: () => const MfSkeleton(height: 48),
          error: (error, _) => MfNotice(
            icon: Icons.error_outline,
            tone: MfNoticeTone.danger,
            message: describeError(error),
          ),
          data: (items) => items.isEmpty
              ? Text(
                  'Aucun commentaire. Écrivez @prénom.nom pour interpeller '
                  'quelqu\'un.',
                  style: Theme.of(context).textTheme.bodySmall,
                )
              : Column(
                  children: [
                    for (final comment in items)
                      _CommentBubble(
                        key: ValueKey(comment.id),
                        entryId: widget.entryId,
                        comment: comment,
                      ),
                  ],
                ),
        ),
        const SizedBox(height: Space.md),
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: _controller,
                minLines: 1,
                maxLines: 4,
                decoration: const InputDecoration(
                  hintText: 'Commenter, ou @mentionner',
                  isDense: true,
                ),
                onSubmitted: (_) => _send(),
              ),
            ),
            const SizedBox(width: Space.sm),
            IconButton.filled(
              onPressed: _sending ? null : _send,
              icon: const Icon(Icons.send, size: 16),
            ),
          ],
        ),
      ],
    );
  }
}

String _unresolvedMessage(List<String> handles) {
  if (handles.length == 1) {
    return '${handles.single} n\'a pas accès à cette note. '
        'Ajoutez cette personne à l\'espace pour que la mention prenne effet.';
  }
  return '${handles.join(', ')} n\'ont pas accès à cette note.';
}

class _CommentBubble extends ConsumerWidget {
  const _CommentBubble({
    required this.entryId,
    required this.comment,
    super.key,
  });

  final String entryId;
  final Comment comment;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: Space.sm),
      padding: const EdgeInsets.all(Space.md),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: Radii.mdAll,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (comment.createdAt != null)
                Text(
                  formatRelativePast(comment.createdAt!),
                  style: theme.textTheme.labelSmall,
                ),
              if (comment.edited) ...[
                const SizedBox(width: Space.sm),
                Text('modifié', style: theme.textTheme.labelSmall),
              ],
              const Spacer(),
              if (comment.resolved)
                const MfChip(label: 'Résolu', icon: Icons.check),
              PopupMenuButton<String>(
                tooltip: 'Actions',
                onSelected: (action) => _apply(context, ref, action),
                itemBuilder: (context) => [
                  if (!comment.resolved)
                    const PopupMenuItem(
                      value: 'resolve',
                      child: Text('Marquer résolu'),
                    ),
                  const PopupMenuItem(
                    value: 'edit',
                    child: Text('Modifier'),
                  ),
                  const PopupMenuItem(
                    value: 'delete',
                    child: Text('Supprimer'),
                  ),
                ],
              ),
            ],
          ),
          Text(comment.body, style: theme.textTheme.bodyMedium),
          if (comment.unresolvedMentions.isNotEmpty) ...[
            const SizedBox(height: Space.sm),
            MfNotice(
              icon: Icons.person_off_outlined,
              tone: MfNoticeTone.warning,
              message: _unresolvedMessage(comment.unresolvedMentions),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _apply(
      BuildContext context, WidgetRef ref, String action) async {
    final actions = ref.read(enterpriseActionsProvider);
    try {
      switch (action) {
        case 'resolve':
          await actions.resolveComment(entryId, comment.id);
        case 'edit':
          final body = await promptForText(
            context,
            title: 'Modifier le commentaire',
            hint: 'Texte',
            initial: comment.body,
          );
          if (body == null || body.trim().isEmpty) return;
          await actions.editComment(entryId, comment.id, body.trim());
        case 'delete':
          await actions.deleteComment(entryId, comment.id);
      }
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }
}
