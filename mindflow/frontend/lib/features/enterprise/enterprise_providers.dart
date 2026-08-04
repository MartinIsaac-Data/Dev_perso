/// State for the enterprise surface.
///
/// Two things here are deliberate and worth reading before adding to them.
///
/// **Actions invalidate; they do not patch.** After adding a member or revoking
/// a link the provider is invalidated and the list refetched. The optimistic
/// alternative — mutating the local list — is faster and wrong here: what the
/// caller is allowed to see is decided by a PostgreSQL policy, so a client-side
/// guess about the new state is a guess about an authorisation decision. Being
/// briefly stale is better than confidently showing a row the server would not.
///
/// **The share token is held in memory, once.** [issuedShareProvider] exists
/// because the plaintext exists for exactly one response and can never be
/// fetched again. It is cleared when the sheet closes, which is honest: the
/// user really has lost it.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/client.dart';
import '../../core/api/enterprise_models.dart';

// --------------------------------------------------------------------------- //
// Reads
// --------------------------------------------------------------------------- //
final workspacesProvider =
    FutureProvider.autoDispose<List<Workspace>>((ref) async {
  return ref.watch(apiProvider).listWorkspaces();
});

final workspaceMembersProvider =
    FutureProvider.autoDispose.family<List<Member>, String>((ref, id) async {
  return ref.watch(apiProvider).workspaceMembers(id);
});

final accountMembersProvider =
    FutureProvider.autoDispose<List<Member>>((ref) async {
  return ref.watch(apiProvider).accountMembers();
});

final invitationsProvider =
    FutureProvider.autoDispose<List<Invitation>>((ref) async {
  return ref.watch(apiProvider).listInvitations();
});

final commentsProvider =
    FutureProvider.autoDispose.family<List<Comment>, String>((ref, entryId) {
  return ref.watch(apiProvider).listComments(entryId);
});

final mentionsProvider = FutureProvider.autoDispose<List<Mention>>((ref) {
  return ref.watch(apiProvider).listMentions();
});

/// Selects only the count, so the shell badge does not rebuild when the mention
/// list changes underneath it.
final unreadMentionsProvider = Provider.autoDispose<int>((ref) {
  return ref.watch(mentionsProvider).maybeWhen(
        data: (mentions) => mentions.where((mention) => !mention.read).length,
        orElse: () => 0,
      );
});

final sharesProvider = FutureProvider.autoDispose<List<ShareLink>>((ref) {
  return ref.watch(apiProvider).listShares();
});

final integrationsProvider =
    FutureProvider.autoDispose<List<Connection>>((ref) {
  return ref.watch(apiProvider).listIntegrations();
});

final conflictsProvider = FutureProvider.autoDispose<List<SyncConflict>>((ref) {
  return ref.watch(apiProvider).listConflicts();
});

final overviewProvider = FutureProvider.autoDispose<AccountOverview>((ref) {
  return ref.watch(apiProvider).adminOverview();
});

final auditFilterProvider = StateProvider.autoDispose<String>((ref) => '');

final auditProvider = FutureProvider.autoDispose<List<AuditEntry>>((ref) {
  final action = ref.watch(auditFilterProvider);
  return ref.watch(apiProvider).auditLog(action: action);
});

final usageProvider = FutureProvider.autoDispose<List<UsagePoint>>((ref) {
  return ref.watch(apiProvider).adminUsage();
});

final healthProvider = FutureProvider.autoDispose<OperationalHealth>((ref) {
  return ref.watch(apiProvider).adminHealth();
});

/// The share link that was just minted, plaintext included. Null the rest of
/// the time — see the library doc.
final issuedShareProvider = StateProvider<ShareLink?>((ref) => null);

// --------------------------------------------------------------------------- //
// Writes
// --------------------------------------------------------------------------- //
class EnterpriseActions {
  EnterpriseActions(this._ref);

  final Ref _ref;

  MindflowApi get _api => _ref.read(apiProvider);

  Future<Workspace> createWorkspace(String name, {String? description}) async {
    final workspace =
        await _api.createWorkspace(name: name, description: description);
    _ref.invalidate(workspacesProvider);
    return workspace;
  }

  Future<void> renameWorkspace(String id, String name) async {
    await _api.updateWorkspace(id, name: name);
    _ref.invalidate(workspacesProvider);
  }

  Future<void> archiveWorkspace(String id) async {
    await _api.deleteWorkspace(id);
    _ref.invalidate(workspacesProvider);
  }

  Future<void> addWorkspaceMember(
    String workspaceId,
    String userId,
    WorkspaceRole role,
  ) async {
    await _api.addWorkspaceMember(workspaceId, userId: userId, role: role);
    _ref.invalidate(workspaceMembersProvider(workspaceId));
  }

  Future<void> removeWorkspaceMember(String workspaceId, String userId) async {
    await _api.removeWorkspaceMember(workspaceId, userId);
    _ref.invalidate(workspaceMembersProvider(workspaceId));
  }

  Future<void> setMemberRole(String userId, AccountRole role) async {
    await _api.setMemberRole(userId, role);
    _ref.invalidate(accountMembersProvider);
  }

  Future<void> removeMember(String userId) async {
    await _api.removeMember(userId);
    _ref.invalidate(accountMembersProvider);
  }

  Future<Invitation> invite(String email, AccountRole role) async {
    final invitation = await _api.invite(email: email, role: role);
    _ref.invalidate(invitationsProvider);
    return invitation;
  }

  Future<void> revokeInvitation(String id) async {
    await _api.revokeInvitation(id);
    _ref.invalidate(invitationsProvider);
  }

  Future<Comment> comment(String entryId, String body) async {
    final comment = await _api.postComment(entryId, body);
    _ref.invalidate(commentsProvider(entryId));
    return comment;
  }

  Future<void> editComment(
      String entryId, String commentId, String body) async {
    await _api.editComment(commentId, body);
    _ref.invalidate(commentsProvider(entryId));
  }

  Future<void> deleteComment(String entryId, String commentId) async {
    await _api.deleteComment(commentId);
    _ref.invalidate(commentsProvider(entryId));
  }

  Future<void> resolveComment(String entryId, String commentId) async {
    await _api.resolveComment(commentId);
    _ref.invalidate(commentsProvider(entryId));
  }

  Future<void> markMentionRead(String mentionId) async {
    await _api.markMentionRead(mentionId);
    _ref.invalidate(mentionsProvider);
  }

  /// Mints a link and parks the plaintext in [issuedShareProvider]. The caller
  /// must show it immediately; there is no second chance.
  Future<ShareLink> share(
    String entryId, {
    DateTime? expiresAt,
    bool allowComments = false,
  }) async {
    final link = await _api.shareEntry(
      entryId,
      expiresAt: expiresAt,
      allowComments: allowComments,
    );
    _ref.read(issuedShareProvider.notifier).state = link;
    _ref.invalidate(sharesProvider);
    return link;
  }

  Future<void> revokeShare(String linkId) async {
    await _api.revokeShare(linkId);
    _ref.invalidate(sharesProvider);
  }

  Future<Connection> connect({
    required SyncProvider provider,
    required String accessToken,
    SyncDirection direction = SyncDirection.pull,
  }) async {
    final connection = await _api.connectIntegration(
      provider: provider,
      accessToken: accessToken,
      direction: direction,
    );
    _ref.invalidate(integrationsProvider);
    return connection;
  }

  Future<void> disconnect(String connectionId) async {
    await _api.disconnectIntegration(connectionId);
    _ref.invalidate(integrationsProvider);
  }

  Future<SyncReport> syncNow(String connectionId) async {
    final report = await _api.syncNow(connectionId);
    _ref
      ..invalidate(integrationsProvider)
      ..invalidate(conflictsProvider);
    return report;
  }

  Future<void> resolveConflict(String linkId, {required bool keepLocal}) async {
    await _api.resolveConflict(linkId, keep: keepLocal ? 'local' : 'remote');
    _ref.invalidate(conflictsProvider);
  }
}

final enterpriseActionsProvider =
    Provider<EnterpriseActions>(EnterpriseActions.new);
