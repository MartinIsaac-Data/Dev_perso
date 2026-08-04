/// Where somebody asked you something by name.
///
/// Separate from the notification centre on purpose. A mention is the one
/// notification a person may reasonably want while muting everything else —
/// somebody addressed them directly and is waiting — and burying it among
/// reminders and digests is how it gets missed.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/enterprise_models.dart';
import '../../core/api/errors.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import '../../app/router.dart';
import 'enterprise_providers.dart';
import 'enterprise_ui.dart';

class MentionsScreen extends ConsumerWidget {
  const MentionsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mentions = ref.watch(mentionsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Mentions')),
      body: mentions.when(
        loading: () => const MfSkeletonList(rows: 5),
        error: (error, _) => MfEmpty(
          icon: Icons.error_outline,
          title: 'Impossible de charger les mentions',
          message: describeError(error),
        ),
        data: (items) => items.isEmpty
            ? const MfEmpty(
                icon: Icons.alternate_email,
                title: 'Aucune mention',
                message: 'Quand un collègue écrit @votre.nom dans un '
                    'commentaire, cela apparaît ici.',
              )
            : ListView.builder(
                padding: const EdgeInsets.symmetric(vertical: Space.md),
                itemCount: items.length,
                itemBuilder: (context, index) => _MentionTile(
                  mention: items[index],
                  onOpen: () => _open(context, ref, items[index]),
                ),
              ),
      ),
    );
  }

  /// Marks read *then* navigates. The other order leaves a mention unread when
  /// the user backs out of the note, which reads as the product having lost it.
  Future<void> _open(
      BuildContext context, WidgetRef ref, Mention mention) async {
    try {
      if (!mention.read) {
        await ref.read(enterpriseActionsProvider).markMentionRead(mention.id);
      }
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
      return;
    }
    if (context.mounted) context.go(Routes.notes);
  }
}

class _MentionTile extends StatelessWidget {
  const _MentionTile({required this.mention, required this.onOpen});

  final Mention mention;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: mention.read
            ? theme.colorScheme.surfaceContainerHigh
            : theme.colorScheme.primaryContainer,
        child: Icon(
          Icons.alternate_email,
          size: 16,
          color: mention.read
              ? theme.colorScheme.onSurfaceVariant
              : theme.colorScheme.onPrimaryContainer,
        ),
      ),
      title: Text(
        '@${mention.handle}',
        style: theme.textTheme.bodyMedium?.copyWith(
          fontWeight: mention.read ? FontWeight.w400 : FontWeight.w600,
        ),
      ),
      subtitle: Text(
        mention.createdAt == null
            ? 'Dans un commentaire'
            : 'Dans un commentaire · ${formatRelativePast(mention.createdAt!)}',
      ),
      onTap: onOpen,
    );
  }
}
