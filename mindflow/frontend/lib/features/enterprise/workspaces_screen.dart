/// Workspaces, and who is in them.
///
/// The empty state carries the product's most important sentence about
/// collaboration: a note outside a workspace is private, including from an
/// administrator. Saying it here, before anybody has created anything, is the
/// only moment a user reads it — after the first workspace exists, this screen
/// is a list and nobody reads lists.
///
/// Archiving rather than deleting is surfaced in the wording too. « Archiver »
/// on the button and « Le contenu n'est pas supprimé » under it, because a
/// destructive-sounding verb on a non-destructive action makes people hesitate
/// where they need not, and the reverse gets somebody's work deleted.
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

class WorkspacesScreen extends ConsumerWidget {
  const WorkspacesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final workspaces = ref.watch(workspacesProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Espaces'),
        actions: [
          IconButton(
            tooltip: 'Nouvel espace',
            onPressed: () => _createWorkspace(context, ref),
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      body: workspaces.when(
        loading: () => const MfSkeletonList(rows: 4),
        error: (error, _) => MfEmpty(
          icon: Icons.error_outline,
          title: 'Impossible de charger les espaces',
          message: describeError(error),
        ),
        data: (items) => items.isEmpty
            ? MfEmpty(
                icon: Icons.workspaces_outline,
                title: 'Aucun espace',
                message: 'Une note sans espace reste privée — y compris pour '
                    "l'administrateur du compte. Créez un espace pour "
                    'partager avec vos collègues.',
                action: FilledButton.icon(
                  onPressed: () => _createWorkspace(context, ref),
                  icon: const Icon(Icons.add, size: 16),
                  label: const Text('Créer un espace'),
                ),
              )
            : ListView.builder(
                padding: const EdgeInsets.symmetric(vertical: Space.md),
                itemCount: items.length,
                itemExtent: 76,
                findChildIndexCallback: (key) {
                  final id = (key as ValueKey<String>).value;
                  final index =
                      items.indexWhere((workspace) => workspace.id == id);
                  return index < 0 ? null : index;
                },
                itemBuilder: (context, index) => _WorkspaceTile(
                  key: ValueKey(items[index].id),
                  workspace: items[index],
                ),
              ),
      ),
    );
  }
}

Future<void> _createWorkspace(BuildContext context, WidgetRef ref) async {
  final name = await promptForText(
    context,
    title: 'Nouvel espace',
    hint: 'Nom de l\'espace',
    confirm: 'Créer',
  );
  if (name == null || name.trim().isEmpty) return;
  try {
    await ref.read(enterpriseActionsProvider).createWorkspace(name.trim());
  } on ApiException catch (error) {
    if (context.mounted) showErrorSnack(context, error);
  }
}

class _WorkspaceTile extends ConsumerWidget {
  const _WorkspaceTile({required this.workspace, super.key});

  final Workspace workspace;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: theme.colorScheme.surfaceContainerHigh,
        child: Icon(
          workspace.archived
              ? Icons.archive_outlined
              : Icons.workspaces_outline,
          size: 18,
          color: theme.colorScheme.onSurfaceVariant,
        ),
      ),
      title: Text(workspace.name),
      subtitle: Text(
        workspace.description?.isNotEmpty == true
            ? workspace.description!
            : (workspace.createdAt == null
                ? ''
                : 'Créé ${formatRelativePast(workspace.createdAt!)}'),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: workspace.archived
          ? const MfChip(label: 'Archivé', icon: Icons.archive_outlined)
          : const Icon(Icons.chevron_right, size: 18),
      onTap: () => showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        builder: (_) => WorkspaceMembersSheet(workspace: workspace),
      ),
    );
  }
}

/// Members of one workspace, and the two things one does to them.
class WorkspaceMembersSheet extends ConsumerWidget {
  const WorkspaceMembersSheet({required this.workspace, super.key});

  final Workspace workspace;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final members = ref.watch(workspaceMembersProvider(workspace.id));
    final theme = Theme.of(context);

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(Space.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child:
                      Text(workspace.name, style: theme.textTheme.titleMedium),
                ),
                IconButton(
                  tooltip: 'Ajouter un membre',
                  onPressed: () => _addMember(context, ref),
                  icon: const Icon(Icons.person_add_alt),
                ),
              ],
            ),
            const SizedBox(height: Space.sm),
            const MfNotice(
              icon: Icons.lock_outline,
              message: 'Seules les notes placées dans cet espace sont visibles '
                  'par ses membres. Les autres restent privées.',
            ),
            const MfSectionHeader(title: 'Membres'),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: members.when(
                loading: () => const MfSkeletonList(rows: 3),
                error: (error, _) => MfNotice(
                  icon: Icons.error_outline,
                  tone: MfNoticeTone.danger,
                  message: describeError(error),
                ),
                data: (people) => people.isEmpty
                    ? const MfEmpty(
                        icon: Icons.group_outlined,
                        title: 'Personne pour l\'instant',
                        message:
                            'Ajoutez un collègue pour partager cet espace.',
                      )
                    : ListView.builder(
                        shrinkWrap: true,
                        itemCount: people.length,
                        itemBuilder: (context, index) => _MemberRow(
                          member: people[index],
                          onRemove: () => _remove(context, ref, people[index]),
                        ),
                      ),
              ),
            ),
            const SizedBox(height: Space.lg),
            OutlinedButton.icon(
              onPressed: () => _archive(context, ref),
              icon: const Icon(Icons.archive_outlined, size: 16),
              label: const Text('Archiver cet espace'),
            ),
            Padding(
              padding: const EdgeInsets.only(top: Space.xs),
              child: Text(
                'Le contenu n\'est pas supprimé : les notes redeviennent '
                'privées à leur auteur.',
                style: theme.textTheme.bodySmall,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _addMember(BuildContext context, WidgetRef ref) async {
    final candidates = await ref.read(accountMembersProvider.future);
    if (!context.mounted) return;
    final existing =
        await ref.read(workspaceMembersProvider(workspace.id).future);
    if (!context.mounted) return;

    final ids = existing.map((member) => member.userId).toSet();
    final available =
        candidates.where((member) => !ids.contains(member.userId)).toList();
    if (available.isEmpty) {
      showMessage(context, 'Tout le compte est déjà dans cet espace.');
      return;
    }

    final chosen = await showModalBottomSheet<(Member, WorkspaceRole)>(
      context: context,
      builder: (_) => _AddMemberSheet(candidates: available),
    );
    if (chosen == null || !context.mounted) return;
    try {
      await ref.read(enterpriseActionsProvider).addWorkspaceMember(
            workspace.id,
            chosen.$1.userId,
            chosen.$2,
          );
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }

  Future<void> _remove(
      BuildContext context, WidgetRef ref, Member member) async {
    try {
      await ref
          .read(enterpriseActionsProvider)
          .removeWorkspaceMember(workspace.id, member.userId);
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }

  Future<void> _archive(BuildContext context, WidgetRef ref) async {
    try {
      await ref.read(enterpriseActionsProvider).archiveWorkspace(workspace.id);
      if (context.mounted) Navigator.of(context).pop();
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }
}

class _MemberRow extends StatelessWidget {
  const _MemberRow({required this.member, required this.onRemove});

  final Member member;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      dense: true,
      title: Text(member.label),
      subtitle: Text('@${member.handle}'),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          MfChip(label: (member.workspaceRole ?? WorkspaceRole.reader).label),
          IconButton(
            tooltip: 'Retirer de l\'espace',
            onPressed: onRemove,
            icon: const Icon(Icons.close, size: 16),
          ),
        ],
      ),
    );
  }
}

class _AddMemberSheet extends StatefulWidget {
  const _AddMemberSheet({required this.candidates});

  final List<Member> candidates;

  @override
  State<_AddMemberSheet> createState() => _AddMemberSheetState();
}

class _AddMemberSheetState extends State<_AddMemberSheet> {
  WorkspaceRole _role = WorkspaceRole.editor;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.all(Space.lg),
            child: Row(
              children: [
                Text('Rôle dans l\'espace',
                    style: Theme.of(context).textTheme.labelLarge),
                const Spacer(),
                for (final role in WorkspaceRole.values)
                  Padding(
                    padding: const EdgeInsets.only(left: Space.xs),
                    child: MfChip(
                      label: role.label,
                      selected: _role == role,
                      onTap: () => setState(() => _role = role),
                    ),
                  ),
              ],
            ),
          ),
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: widget.candidates.length,
              itemBuilder: (context, index) {
                final member = widget.candidates[index];
                return ListTile(
                  dense: true,
                  title: Text(member.label),
                  subtitle: Text(member.email),
                  onTap: () => Navigator.of(context).pop((member, _role)),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
