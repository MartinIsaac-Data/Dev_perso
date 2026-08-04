/// The account's people: members, pending invitations, and live share links.
///
/// Three lists on one screen because they answer one question — *who can see
/// what?* — and a share link is a member of that answer even though it belongs
/// to nobody. Splitting them across three destinations would make "who has
/// access" take three navigations, which is how it stops being checked.
///
/// The share list shows a suffix, never a token. The server keeps only a
/// digest, so it *cannot* show one; saying « …4f2a » lets somebody recognise a
/// link they are about to revoke without the product having to be able to
/// reproduce it.
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

class TeamScreen extends ConsumerStatefulWidget {
  const TeamScreen({super.key});

  @override
  ConsumerState<TeamScreen> createState() => _TeamScreenState();
}

class _TeamScreenState extends ConsumerState<TeamScreen>
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
        title: const Text('Équipe'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'Membres'),
            Tab(text: 'Invitations'),
            Tab(text: 'Liens partagés'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: const [_MembersPanel(), _InvitationsPanel(), _SharesPanel()],
      ),
    );
  }
}

class _MembersPanel extends ConsumerWidget {
  const _MembersPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final members = ref.watch(accountMembersProvider);

    return members.when(
      loading: () => const MfSkeletonList(rows: 5),
      error: (error, _) => MfEmpty(
        icon: Icons.error_outline,
        title: 'Impossible de charger les membres',
        message: describeError(error),
      ),
      data: (people) => ListView.builder(
        padding: const EdgeInsets.symmetric(vertical: Space.md),
        itemCount: people.length,
        itemBuilder: (context, index) {
          final member = people[index];
          return ListTile(
            title: Text(member.label),
            subtitle: Text(member.email),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                MfChip(label: member.role.label),
                PopupMenuButton<_MemberAction>(
                  tooltip: 'Modifier',
                  onSelected: (action) => _apply(context, ref, member, action),
                  itemBuilder: (context) => [
                    for (final role in AccountRole.values)
                      if (role != member.role)
                        PopupMenuItem(
                          value: _MemberAction.role(role),
                          child: Text('Passer ${role.label.toLowerCase()}'),
                        ),
                    const PopupMenuDivider(),
                    const PopupMenuItem(
                      value: _MemberAction.remove(),
                      child: Text('Retirer du compte'),
                    ),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _apply(
    BuildContext context,
    WidgetRef ref,
    Member member,
    _MemberAction action,
  ) async {
    final actions = ref.read(enterpriseActionsProvider);
    try {
      if (action.role != null) {
        await actions.setMemberRole(member.userId, action.role!);
        return;
      }
      // Removal is the one irreversible action on this screen, and the server
      // refuses the two cases that would lock the account — last owner, and a
      // member of higher rank. Asking first means the refusal is a rule the
      // user meets deliberately rather than by accident.
      final confirmed = await confirmDestructive(
        context,
        title: 'Retirer ${member.label} ?',
        message: 'Cette personne perdra l\'accès à tous les espaces du compte. '
            'Ses notes personnelles ne sont pas supprimées.',
        confirm: 'Retirer',
      );
      if (!confirmed) return;
      await actions.removeMember(member.userId);
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }
}

/// A menu choice: either a new role, or removal. A sealed pair would be
/// heavier than this is worth, but a nullable role keeps the two distinguishable
/// without a magic sentinel.
class _MemberAction {
  const _MemberAction.role(this.role);
  const _MemberAction.remove() : role = null;

  final AccountRole? role;
}

class _InvitationsPanel extends ConsumerWidget {
  const _InvitationsPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final invitations = ref.watch(invitationsProvider);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(Space.lg),
          child: FilledButton.icon(
            onPressed: () => _invite(context, ref),
            icon: const Icon(Icons.mail_outline, size: 16),
            label: const Text('Inviter quelqu\'un'),
          ),
        ),
        Expanded(
          child: invitations.when(
            loading: () => const MfSkeletonList(rows: 3),
            error: (error, _) => MfEmpty(
              icon: Icons.error_outline,
              title: 'Impossible de charger les invitations',
              message: describeError(error),
            ),
            data: (pending) => pending.isEmpty
                ? const MfEmpty(
                    icon: Icons.mail_outline,
                    title: 'Aucune invitation en attente',
                    message:
                        'Les invitations expirent : une invitation oubliée '
                        'ne reste pas ouverte indéfiniment.',
                  )
                : ListView.builder(
                    itemCount: pending.length,
                    itemBuilder: (context, index) {
                      final invitation = pending[index];
                      return ListTile(
                        title: Text(invitation.email),
                        subtitle: Text(
                          invitation.expiresAt == null
                              ? invitation.role.label
                              : '${invitation.role.label} · expire '
                                  '${formatDay(invitation.expiresAt!)}',
                        ),
                        trailing: IconButton(
                          tooltip: 'Révoquer',
                          onPressed: () => _revoke(context, ref, invitation),
                          icon: const Icon(Icons.close, size: 18),
                        ),
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }

  Future<void> _invite(BuildContext context, WidgetRef ref) async {
    final email = await promptForText(
      context,
      title: 'Inviter',
      hint: 'adresse@exemple.fr',
      confirm: 'Envoyer',
      helper: 'La personne rejoindra ce compte avec le rôle « Membre ».',
    );
    if (email == null || email.trim().isEmpty) return;
    try {
      await ref
          .read(enterpriseActionsProvider)
          .invite(email.trim(), AccountRole.member);
      if (context.mounted) showMessage(context, 'Invitation envoyée.');
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }

  Future<void> _revoke(
      BuildContext context, WidgetRef ref, Invitation invitation) async {
    try {
      await ref.read(enterpriseActionsProvider).revokeInvitation(invitation.id);
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }
}

class _SharesPanel extends ConsumerWidget {
  const _SharesPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final shares = ref.watch(sharesProvider);

    return shares.when(
      loading: () => const MfSkeletonList(rows: 4),
      error: (error, _) => MfEmpty(
        icon: Icons.error_outline,
        title: 'Impossible de charger les liens',
        message: describeError(error),
      ),
      data: (links) => links.isEmpty
          ? const MfEmpty(
              icon: Icons.link_off,
              title: 'Aucun lien actif',
              message: 'Un lien de partage donne accès à une note, en lecture, '
                  'à qui le possède. Ils expirent au bout de trente jours.',
            )
          : ListView.builder(
              padding: const EdgeInsets.symmetric(vertical: Space.md),
              itemCount: links.length,
              itemBuilder: (context, index) {
                final link = links[index];
                return ListTile(
                  leading: Icon(
                    link.live ? Icons.link : Icons.link_off,
                    size: 18,
                  ),
                  // The suffix, never the token: the server keeps a digest.
                  title: Text('Lien …${link.tokenSuffix}'),
                  subtitle: Text(_subtitle(link)),
                  trailing: link.revoked
                      ? const MfChip(label: 'Révoqué')
                      : IconButton(
                          tooltip: 'Révoquer',
                          onPressed: () => _revoke(context, ref, link),
                          icon: const Icon(Icons.block, size: 18),
                        ),
                );
              },
            ),
    );
  }

  String _subtitle(ShareLink link) {
    final views =
        link.viewCount == 1 ? '1 ouverture' : '${link.viewCount} ouvertures';
    // Revocation is stated before expiry — it is what the owner did, and it is
    // what they should read back.
    if (link.revoked) return 'Révoqué · $views';
    if (link.expired) return 'Expiré · $views';
    if (link.expiresAt == null) return 'Sans expiration · $views';
    return 'Expire ${formatDay(link.expiresAt!)} · $views';
  }

  Future<void> _revoke(
      BuildContext context, WidgetRef ref, ShareLink link) async {
    final confirmed = await confirmDestructive(
      context,
      title: 'Révoquer ce lien ?',
      message: 'Il cessera immédiatement de fonctionner pour tout le monde. '
          'Cette action est définitive.',
      confirm: 'Révoquer',
    );
    if (!confirmed) return;
    try {
      await ref.read(enterpriseActionsProvider).revokeShare(link.id);
    } on ApiException catch (error) {
      if (context.mounted) showErrorSnack(context, error);
    }
  }
}
