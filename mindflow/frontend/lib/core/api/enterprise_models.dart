/// Models for the enterprise layer: workspaces, members, comments, mentions,
/// share links, integrations, administration (API.md §16-17).
///
/// Two of these carry a product decision rather than data.
///
/// [ShareLink.token] is non-null in exactly one place — the response that
/// created it. The server stores only a digest, so it *cannot* be shown again.
/// Making the field nullable rather than a separate type keeps that fact in the
/// type system: any screen that shows a token has to deal with it being absent.
///
/// [Comment.unresolvedMentions] exists so the interface can say « Paul n'a pas
/// accès à cette note ». Without it a mention into a workspace somebody is not
/// in would resolve to nothing and the author would believe they had been
/// notified — a silent failure being the worst kind.
library;

import 'models.dart' show parseDate;
import 'planning_models.dart' show asMap;

// --------------------------------------------------------------------------- //
// Roles
// --------------------------------------------------------------------------- //

/// Account-level role. Ordered: [rank] is what makes "cannot remove somebody
/// above you" expressible without a table of special cases.
enum AccountRole {
  owner,
  admin,
  member,
  viewer;

  static AccountRole parse(String? value) => switch (value) {
        'owner' => AccountRole.owner,
        'admin' => AccountRole.admin,
        'viewer' => AccountRole.viewer,
        _ => AccountRole.member,
      };

  String get param => name;

  String get label => switch (this) {
        AccountRole.owner => 'Propriétaire',
        AccountRole.admin => 'Administrateur',
        AccountRole.member => 'Membre',
        AccountRole.viewer => 'Lecteur',
      };

  int get rank => switch (this) {
        AccountRole.viewer => 0,
        AccountRole.member => 1,
        AccountRole.admin => 2,
        AccountRole.owner => 3,
      };

  bool atLeast(AccountRole other) => rank >= other.rank;
}

/// Workspace-level role. Independent of [AccountRole]: one can be a plain
/// account member and the editor of a single workspace.
enum WorkspaceRole {
  editor,
  commenter,
  reader;

  static WorkspaceRole parse(String? value) => switch (value) {
        'editor' => WorkspaceRole.editor,
        'reader' => WorkspaceRole.reader,
        _ => WorkspaceRole.commenter,
      };

  String get param => name;

  String get label => switch (this) {
        WorkspaceRole.editor => 'Éditeur',
        WorkspaceRole.commenter => 'Commentateur',
        WorkspaceRole.reader => 'Lecteur',
      };

  bool get canComment => this != WorkspaceRole.reader;
  bool get canEdit => this == WorkspaceRole.editor;
}

// --------------------------------------------------------------------------- //
// Workspaces and members
// --------------------------------------------------------------------------- //
class Workspace {
  const Workspace({
    required this.id,
    required this.name,
    this.description,
    this.color,
    this.archived = false,
    this.createdAt,
  });

  final String id;
  final String name;
  final String? description;
  final String? color;
  final bool archived;
  final DateTime? createdAt;

  factory Workspace.fromJson(Map<String, dynamic> json) => Workspace(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? 'Sans nom',
        description: json['description'] as String?,
        color: json['color'] as String?,
        archived: (json['archived'] as bool?) ?? false,
        createdAt: parseDate(json['created_at']),
      );
}

class Member {
  const Member({
    required this.userId,
    required this.email,
    required this.role,
    this.displayName,
    this.workspaceRole,
  });

  final String userId;
  final String email;
  final AccountRole role;
  final String? displayName;

  /// Null when listing the account rather than a workspace. The two are
  /// distinguished by which endpoint produced the list, never conflated.
  final WorkspaceRole? workspaceRole;

  /// What `@` handle would reach this person — the email local part, which is
  /// what the server resolves against.
  String get handle => email.split('@').first;

  String get label =>
      (displayName != null && displayName!.isNotEmpty) ? displayName! : handle;

  factory Member.fromJson(Map<String, dynamic> json) => Member(
        userId: json['user_id'] as String,
        email: (json['email'] as String?) ?? '',
        role: AccountRole.parse(json['role'] as String?),
        displayName: json['display_name'] as String?,
        workspaceRole: json['workspace_role'] == null
            ? null
            : WorkspaceRole.parse(json['workspace_role'] as String?),
      );
}

class Invitation {
  const Invitation({
    required this.id,
    required this.email,
    required this.role,
    this.workspaceId,
    this.token,
    this.expiresAt,
    this.createdAt,
  });

  final String id;
  final String email;
  final AccountRole role;
  final String? workspaceId;

  /// Present once, in the creation response. Same rule as [ShareLink.token].
  final String? token;
  final DateTime? expiresAt;
  final DateTime? createdAt;

  factory Invitation.fromJson(Map<String, dynamic> json) => Invitation(
        id: json['id'] as String,
        email: (json['email'] as String?) ?? '',
        role: AccountRole.parse(json['role'] as String?),
        workspaceId: json['workspace_id'] as String?,
        token: json['token'] as String?,
        expiresAt: parseDate(json['expires_at']),
        createdAt: parseDate(json['created_at']),
      );
}

// --------------------------------------------------------------------------- //
// Comments and mentions
// --------------------------------------------------------------------------- //
class Comment {
  const Comment({
    required this.id,
    required this.entryId,
    required this.authorId,
    required this.body,
    this.parentId,
    this.resolved = false,
    this.edited = false,
    this.createdAt,
    this.mentionedUserIds = const [],
    this.unresolvedMentions = const [],
  });

  final String id;
  final String entryId;
  final String authorId;
  final String body;
  final String? parentId;
  final bool resolved;
  final bool edited;
  final DateTime? createdAt;
  final List<String> mentionedUserIds;

  /// Handles that reached nobody with access to the note. Shown to the author.
  final List<String> unresolvedMentions;

  factory Comment.fromJson(Map<String, dynamic> json) => Comment(
        id: json['id'] as String,
        entryId: json['entry_id'] as String,
        authorId: (json['author_id'] as String?) ?? '',
        body: (json['body'] as String?) ?? '',
        parentId: json['parent_id'] as String?,
        resolved: (json['resolved'] as bool?) ?? false,
        edited: (json['edited'] as bool?) ?? false,
        createdAt: parseDate(json['created_at']),
        mentionedUserIds: _strings(json['mentioned_user_ids']),
        unresolvedMentions: _strings(json['unresolved_mentions']),
      );
}

class Mention {
  const Mention({
    required this.id,
    required this.commentId,
    required this.handle,
    this.read = false,
    this.createdAt,
  });

  final String id;
  final String commentId;
  final String handle;
  final bool read;
  final DateTime? createdAt;

  factory Mention.fromJson(Map<String, dynamic> json) => Mention(
        id: json['id'] as String,
        commentId: (json['comment_id'] as String?) ?? '',
        handle: (json['handle'] as String?) ?? '',
        read: (json['read'] as bool?) ?? false,
        createdAt: parseDate(json['created_at']),
      );
}

// --------------------------------------------------------------------------- //
// Sharing
// --------------------------------------------------------------------------- //
class ShareLink {
  const ShareLink({
    required this.id,
    required this.scope,
    required this.tokenSuffix,
    this.entryId,
    this.token,
    this.expiresAt,
    this.revoked = false,
    this.viewCount = 0,
    this.createdAt,
  });

  final String id;
  final String scope;

  /// The last few characters, so a link can be recognised in a list without the
  /// server having to be able to reproduce it.
  final String tokenSuffix;
  final String? entryId;

  /// Non-null exactly once, in the creation response. See the library doc.
  final String? token;
  final DateTime? expiresAt;
  final bool revoked;
  final int viewCount;
  final DateTime? createdAt;

  bool get expired =>
      expiresAt != null && expiresAt!.isBefore(DateTime.now().toUtc());

  /// Revocation is checked before expiry — that is what the holder's owner did,
  /// and it is what they should be told.
  bool get live => !revoked && !expired;

  factory ShareLink.fromJson(Map<String, dynamic> json) => ShareLink(
        id: json['id'] as String,
        scope: (json['scope'] as String?) ?? 'entry',
        tokenSuffix: (json['token_suffix'] as String?) ?? '',
        entryId: json['entry_id'] as String?,
        token: json['token'] as String?,
        expiresAt: parseDate(json['expires_at']),
        revoked: (json['revoked'] as bool?) ?? false,
        viewCount: (json['view_count'] as num?)?.toInt() ?? 0,
        createdAt: parseDate(json['created_at']),
      );
}

// --------------------------------------------------------------------------- //
// Integrations
// --------------------------------------------------------------------------- //
enum SyncProvider {
  googleCalendar,
  outlookCalendar,
  microsoftTodo,
  slack,
  teams,
  notion,
  obsidian,
  unknown;

  static SyncProvider parse(String? value) => switch (value) {
        'google_calendar' => SyncProvider.googleCalendar,
        'outlook_calendar' => SyncProvider.outlookCalendar,
        'microsoft_todo' => SyncProvider.microsoftTodo,
        'slack' => SyncProvider.slack,
        'teams' => SyncProvider.teams,
        'notion' => SyncProvider.notion,
        'obsidian' => SyncProvider.obsidian,
        _ => SyncProvider.unknown,
      };

  String get param => switch (this) {
        SyncProvider.googleCalendar => 'google_calendar',
        SyncProvider.outlookCalendar => 'outlook_calendar',
        SyncProvider.microsoftTodo => 'microsoft_todo',
        SyncProvider.slack => 'slack',
        SyncProvider.teams => 'teams',
        SyncProvider.notion => 'notion',
        SyncProvider.obsidian => 'obsidian',
        SyncProvider.unknown => 'unknown',
      };

  String get label => switch (this) {
        SyncProvider.googleCalendar => 'Google Calendar',
        SyncProvider.outlookCalendar => 'Outlook Calendar',
        SyncProvider.microsoftTodo => 'Microsoft To Do',
        SyncProvider.slack => 'Slack',
        SyncProvider.teams => 'Microsoft Teams',
        SyncProvider.notion => 'Notion',
        SyncProvider.obsidian => 'Obsidian',
        SyncProvider.unknown => 'Service',
      };

  /// What the connection actually does, in one line. Shown on the connect card
  /// because "connect Slack" tells nobody which direction data will move.
  String get summary => switch (this) {
        SyncProvider.googleCalendar =>
          'Importe vos événements. Peut écrire vos échéances',
        SyncProvider.outlookCalendar =>
          'Importe vos événements. Peut écrire vos échéances',
        SyncProvider.microsoftTodo =>
          'Synchronise vos tâches dans les deux sens',
        SyncProvider.slack => 'Envoie des rappels dans un canal',
        SyncProvider.teams => 'Envoie des rappels dans un canal',
        SyncProvider.notion => 'Exporte vos notes vers une base Notion',
        SyncProvider.obsidian =>
          'Écrit vos notes en Markdown dans votre coffre local',
        SyncProvider.unknown => '',
      };
}

enum ConnectionStatus {
  active,
  error,
  expired,
  unknown;

  static ConnectionStatus parse(String? value) => switch (value) {
        'active' => ConnectionStatus.active,
        'error' => ConnectionStatus.error,
        'expired' => ConnectionStatus.expired,
        _ => ConnectionStatus.unknown,
      };

  String get label => switch (this) {
        ConnectionStatus.active => 'Connecté',
        ConnectionStatus.error => 'En erreur',
        ConnectionStatus.expired => 'Accès révoqué',
        ConnectionStatus.unknown => 'Inconnu',
      };

  /// `expired` and `error` do not mean the same thing, and conflating them
  /// would offer the wrong remedy: a revoked grant will never recover on a
  /// retry, so the only useful button is "reconnect".
  String get remedy => switch (this) {
        ConnectionStatus.expired =>
          'Le service a révoqué l\'accès. Reconnectez-le : réessayer ne suffira pas',
        ConnectionStatus.error =>
          'Plusieurs échecs consécutifs. La synchronisation a été suspendue',
        _ => '',
      };

  bool get needsAttention =>
      this == ConnectionStatus.error || this == ConnectionStatus.expired;
}

enum SyncDirection {
  pull,
  push,
  twoWay;

  static SyncDirection parse(String? value) => switch (value) {
        'push' => SyncDirection.push,
        'two_way' => SyncDirection.twoWay,
        _ => SyncDirection.pull,
      };

  String get param => switch (this) {
        SyncDirection.pull => 'pull',
        SyncDirection.push => 'push',
        SyncDirection.twoWay => 'two_way',
      };

  String get label => switch (this) {
        SyncDirection.pull => 'Lecture seule',
        SyncDirection.push => 'Écriture seule',
        SyncDirection.twoWay => 'Les deux sens',
      };
}

class Connection {
  const Connection({
    required this.id,
    required this.provider,
    required this.label,
    required this.status,
    required this.direction,
    this.accountLabel,
    this.serverSide = true,
    this.lastSyncAt,
    this.lastError,
    this.consecutiveFailures = 0,
  });

  final String id;
  final SyncProvider provider;
  final String label;
  final ConnectionStatus status;
  final SyncDirection direction;
  final String? accountLabel;

  /// False for Obsidian, which is a folder on a disk rather than a service. The
  /// screen uses this to explain the absence of a "sync now" button instead of
  /// showing one that does nothing.
  final bool serverSide;
  final DateTime? lastSyncAt;
  final String? lastError;
  final int consecutiveFailures;

  bool get needsAttention => status.needsAttention;

  factory Connection.fromJson(Map<String, dynamic> json) => Connection(
        id: json['id'] as String,
        provider: SyncProvider.parse(json['provider'] as String?),
        label: (json['label'] as String?) ?? '',
        status: ConnectionStatus.parse(json['status'] as String?),
        direction: SyncDirection.parse(json['direction'] as String?),
        accountLabel: json['account_label'] as String?,
        serverSide: (json['server_side'] as bool?) ?? true,
        lastSyncAt: parseDate(json['last_sync_at']),
        lastError: json['last_error'] as String?,
        consecutiveFailures:
            (json['consecutive_failures'] as num?)?.toInt() ?? 0,
      );
}

class SyncReport {
  const SyncReport({
    required this.provider,
    this.created = 0,
    this.updated = 0,
    this.unchanged = 0,
    this.deleted = 0,
    this.conflicts = 0,
    this.failed = false,
    this.reason = '',
  });

  final String provider;
  final int created;
  final int updated;
  final int unchanged;
  final int deleted;
  final int conflicts;

  /// True with a 200. A provider outage is not the client's fault and turning
  /// it into a 4xx would make a retry loop out of what the scheduler handles.
  final bool failed;
  final String reason;

  int get changed => created + updated + deleted;

  factory SyncReport.fromJson(Map<String, dynamic> json) => SyncReport(
        provider: (json['provider'] as String?) ?? '',
        created: (json['created'] as num?)?.toInt() ?? 0,
        updated: (json['updated'] as num?)?.toInt() ?? 0,
        unchanged: (json['unchanged'] as num?)?.toInt() ?? 0,
        deleted: (json['deleted'] as num?)?.toInt() ?? 0,
        conflicts: (json['conflicts'] as num?)?.toInt() ?? 0,
        failed: (json['failed'] as bool?) ?? false,
        reason: (json['reason'] as String?) ?? '',
      );
}

class SyncConflict {
  const SyncConflict({
    required this.id,
    required this.provider,
    this.entryId,
    this.externalUrl,
    this.detectedAt,
  });

  final String id;
  final SyncProvider provider;
  final String? entryId;
  final String? externalUrl;
  final DateTime? detectedAt;

  factory SyncConflict.fromJson(Map<String, dynamic> json) => SyncConflict(
        id: json['id'] as String,
        provider: SyncProvider.parse(json['provider'] as String?),
        entryId: json['entry_id'] as String?,
        externalUrl: json['external_url'] as String?,
        detectedAt: parseDate(json['detected_at']),
      );
}

// --------------------------------------------------------------------------- //
// Administration
// --------------------------------------------------------------------------- //
class AccountOverview {
  const AccountOverview({
    this.members = 0,
    this.workspaces = 0,
    this.entries = 0,
    this.captures = 0,
    this.comments = 0,
    this.activeShareLinks = 0,
    this.connectedIntegrations = 0,
    this.integrationsNeedingAttention = 0,
    this.indexedChunks = 0,
    this.pendingChunks = 0,
  });

  final int members;
  final int workspaces;
  final int entries;
  final int captures;
  final int comments;
  final int activeShareLinks;
  final int connectedIntegrations;
  final int integrationsNeedingAttention;
  final int indexedChunks;
  final int pendingChunks;

  factory AccountOverview.fromJson(Map<String, dynamic> json) =>
      AccountOverview(
        members: _int(json['members']),
        workspaces: _int(json['workspaces']),
        entries: _int(json['entries']),
        captures: _int(json['captures']),
        comments: _int(json['comments']),
        activeShareLinks: _int(json['active_share_links']),
        connectedIntegrations: _int(json['connected_integrations']),
        integrationsNeedingAttention:
            _int(json['integrations_needing_attention']),
        indexedChunks: _int(json['indexed_chunks']),
        pendingChunks: _int(json['pending_chunks']),
      );
}

class AuditEntry {
  const AuditEntry({
    required this.id,
    required this.action,
    required this.actorType,
    this.actorUserId,
    this.resourceType,
    this.resourceId,
    this.metadata = const {},
    this.occurredAt,
  });

  final int id;
  final String action;
  final String actorType;
  final String? actorUserId;
  final String? resourceType;
  final String? resourceId;
  final Map<String, dynamic> metadata;
  final DateTime? occurredAt;

  /// `workspace.member.added` → « Membre ajouté à un espace ». Falls back to
  /// the raw action rather than inventing a label for something new — a wrong
  /// French sentence in an audit trail is worse than an untranslated one.
  String get label => switch (action) {
        'workspace.created' => 'Espace créé',
        'workspace.updated' => 'Espace modifié',
        'workspace.archived' => 'Espace archivé',
        'workspace.member.added' => 'Membre ajouté à un espace',
        'workspace.member.removed' => 'Membre retiré d\'un espace',
        'member.role.changed' => 'Rôle modifié',
        'member.removed' => 'Membre retiré du compte',
        'invitation.created' => 'Invitation envoyée',
        'invitation.accepted' => 'Invitation acceptée',
        'invitation.revoked' => 'Invitation révoquée',
        'share.created' => 'Lien de partage créé',
        'share.revoked' => 'Lien de partage révoqué',
        'integration.connected' => 'Service connecté',
        'integration.disconnected' => 'Service déconnecté',
        'comment.deleted' => 'Commentaire supprimé',
        _ => action,
      };

  factory AuditEntry.fromJson(Map<String, dynamic> json) => AuditEntry(
        id: _int(json['id']),
        action: (json['action'] as String?) ?? '',
        actorType: (json['actor_type'] as String?) ?? 'system',
        actorUserId: json['actor_user_id'] as String?,
        resourceType: json['resource_type'] as String?,
        resourceId: json['resource_id'] as String?,
        metadata: asMap(json['metadata']),
        occurredAt: parseDate(json['occurred_at']),
      );
}

class UsagePoint {
  const UsagePoint({
    required this.day,
    this.captures = 0,
    this.entries = 0,
    this.comments = 0,
  });

  final DateTime day;
  final int captures;
  final int entries;
  final int comments;

  int get total => captures + entries + comments;

  factory UsagePoint.fromJson(Map<String, dynamic> json) => UsagePoint(
        day: parseDate(json['day']) ?? DateTime.now(),
        captures: _int(json['captures']),
        entries: _int(json['entries']),
        comments: _int(json['comments']),
      );
}

class OperationalHealth {
  const OperationalHealth({
    this.embeddingBacklog = 0,
    this.oldestPendingChunk,
    this.failingIntegrations = const [],
    this.auditPartitions = 0,
    this.auditPartitionGap = false,
  });

  final int embeddingBacklog;
  final DateTime? oldestPendingChunk;
  final List<String> failingIntegrations;
  final int auditPartitions;

  /// The only field on this screen that predicts an outage rather than
  /// reporting one: next month has no partition, so every audit write will
  /// fail on the 1st.
  final bool auditPartitionGap;

  bool get healthy => !auditPartitionGap && failingIntegrations.isEmpty;

  factory OperationalHealth.fromJson(Map<String, dynamic> json) =>
      OperationalHealth(
        embeddingBacklog: _int(json['embedding_backlog']),
        oldestPendingChunk: parseDate(json['oldest_pending_chunk']),
        failingIntegrations: _strings(json['failing_integrations']),
        auditPartitions: _int(json['audit_partitions']),
        auditPartitionGap: (json['audit_partition_gap'] as bool?) ?? false,
      );
}

int _int(dynamic value) => (value as num?)?.toInt() ?? 0;

List<String> _strings(dynamic value) => value is List
    ? value.map((item) => item.toString()).toList(growable: false)
    : const <String>[];
