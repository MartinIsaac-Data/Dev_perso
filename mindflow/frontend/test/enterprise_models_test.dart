/// Parsing the enterprise payloads.
///
/// The tests that matter here are the ones about *absence*. A share token that
/// silently parses to an empty string would let the sheet show a blank link and
/// call it a success; a `server_side` flag defaulting the wrong way would put a
/// « Synchroniser » button on Obsidian, where it does nothing.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/enterprise_models.dart';

void main() {
  group('AccountRole', () {
    test('maps every wire value', () {
      expect(AccountRole.parse('owner'), AccountRole.owner);
      expect(AccountRole.parse('admin'), AccountRole.admin);
      expect(AccountRole.parse('member'), AccountRole.member);
      expect(AccountRole.parse('viewer'), AccountRole.viewer);
    });

    test('an unknown role degrades to member, never to owner', () {
      // The direction of the fallback is the whole point: a client that has not
      // shipped yet must not treat a new role as the most powerful one.
      expect(AccountRole.parse('superadmin'), AccountRole.member);
      expect(AccountRole.parse(null), AccountRole.member);
    });

    test('ranks are ordered so "cannot remove somebody above you" is sayable',
        () {
      expect(AccountRole.owner.atLeast(AccountRole.admin), isTrue);
      expect(AccountRole.admin.atLeast(AccountRole.member), isTrue);
      expect(AccountRole.member.atLeast(AccountRole.admin), isFalse);
      expect(AccountRole.viewer.atLeast(AccountRole.member), isFalse);
    });

    test('every role has a French label', () {
      for (final role in AccountRole.values) {
        expect(role.label, isNotEmpty);
      }
    });
  });

  group('WorkspaceRole', () {
    test('a reader cannot comment, a commenter cannot edit', () {
      expect(WorkspaceRole.reader.canComment, isFalse);
      expect(WorkspaceRole.commenter.canComment, isTrue);
      expect(WorkspaceRole.commenter.canEdit, isFalse);
      expect(WorkspaceRole.editor.canEdit, isTrue);
    });

    test('an unknown role degrades to commenter, not editor', () {
      expect(WorkspaceRole.parse('overlord'), WorkspaceRole.commenter);
    });
  });

  group('Member', () {
    test('derives the mention handle from the email local part', () {
      // This is what the server resolves against, so the client must not invent
      // its own rule — a handle the server would not match is a mention that
      // silently reaches nobody.
      final member = Member.fromJson({
        'user_id': '018f',
        'email': 'marie.dupont@exemple.fr',
        'role': 'member',
      });
      expect(member.handle, 'marie.dupont');
    });

    test('falls back to the handle when there is no display name', () {
      final member = Member.fromJson({
        'user_id': '018f',
        'email': 'paul@exemple.fr',
        'role': 'admin',
      });
      expect(member.label, 'paul');
    });

    test('workspace_role stays null on an account-wide listing', () {
      // Null and "reader" are different facts. Conflating them would show a
      // workspace role for somebody who is in no workspace.
      final member = Member.fromJson({
        'user_id': '018f',
        'email': 'paul@exemple.fr',
        'role': 'member',
      });
      expect(member.workspaceRole, isNull);
    });
  });

  group('Comment', () {
    test('parses unresolved mentions', () {
      final comment = Comment.fromJson({
        'id': '018f',
        'entry_id': '018e',
        'author_id': '018d',
        'body': '@paul peux-tu confirmer ?',
        'status': 'open',
        'mentioned_user_ids': <String>[],
        'unresolved_mentions': ['paul'],
      });
      expect(comment.unresolvedMentions, ['paul']);
      expect(comment.mentionedUserIds, isEmpty);
    });

    test('a missing mentions list parses to empty, not to null', () {
      final comment = Comment.fromJson({
        'id': '018f',
        'entry_id': '018e',
        'author_id': '018d',
        'body': 'Rien à signaler',
        'status': 'open',
      });
      expect(comment.unresolvedMentions, isEmpty);
      expect(comment.mentionedUserIds, isEmpty);
    });
  });

  group('ShareLink', () {
    test('carries the plaintext token only when the server sent one', () {
      final issued = ShareLink.fromJson({
        'id': '018f',
        'scope': 'entry',
        'token': 'xK9abc',
        'token_suffix': '9abc',
      });
      final listed = ShareLink.fromJson({
        'id': '018f',
        'scope': 'entry',
        'token_suffix': '9abc',
      });

      expect(issued.token, 'xK9abc');
      // Only a digest is stored, so a listing cannot produce the plaintext —
      // and null says that, where '' would look like an empty link.
      expect(listed.token, isNull);
      expect(listed.tokenSuffix, '9abc');
    });

    test('a revoked link is not live even if it has not expired', () {
      final link = ShareLink.fromJson({
        'id': '018f',
        'scope': 'entry',
        'token_suffix': '9abc',
        'revoked': true,
        'expires_at': DateTime.now()
            .toUtc()
            .add(const Duration(days: 5))
            .toIso8601String(),
      });
      expect(link.revoked, isTrue);
      expect(link.expired, isFalse);
      expect(link.live, isFalse);
    });

    test('an expired link is not live', () {
      final link = ShareLink.fromJson({
        'id': '018f',
        'scope': 'entry',
        'token_suffix': '9abc',
        'expires_at': DateTime.now()
            .toUtc()
            .subtract(const Duration(days: 1))
            .toIso8601String(),
      });
      expect(link.expired, isTrue);
      expect(link.live, isFalse);
    });

    test('a link without an expiry is live', () {
      final link = ShareLink.fromJson({
        'id': '018f',
        'scope': 'entry',
        'token_suffix': '9abc',
      });
      expect(link.live, isTrue);
    });
  });

  group('SyncProvider', () {
    test('round-trips every wire value', () {
      for (final provider in SyncProvider.values) {
        if (provider == SyncProvider.unknown) continue;
        expect(SyncProvider.parse(provider.param), provider);
      }
    });

    test('an unknown provider does not crash the screen', () {
      expect(SyncProvider.parse('carrier_pigeon'), SyncProvider.unknown);
    });

    test('every provider says what it does', () {
      for (final provider in SyncProvider.values) {
        if (provider == SyncProvider.unknown) continue;
        expect(provider.label, isNotEmpty);
        expect(provider.summary, isNotEmpty,
            reason: '"Connecter Slack" tells nobody which way data moves');
      }
    });
  });

  group('ConnectionStatus', () {
    test('expired and error are distinct, with distinct remedies', () {
      // Conflating them offers the wrong fix: a revoked grant will never
      // recover on a retry, so "réessayer" would be a loop that cannot end.
      expect(ConnectionStatus.expired, isNot(ConnectionStatus.error));
      expect(ConnectionStatus.expired.remedy, contains('Reconnectez'));
      expect(ConnectionStatus.error.remedy, isNot(contains('Reconnectez')));
      expect(ConnectionStatus.expired.needsAttention, isTrue);
      expect(ConnectionStatus.error.needsAttention, isTrue);
      expect(ConnectionStatus.active.needsAttention, isFalse);
    });
  });

  group('Connection', () {
    test('server_side defaults to true so absence is not silently non-server',
        () {
      final connection = Connection.fromJson({
        'id': '018f',
        'provider': 'google_calendar',
        'label': 'Agenda',
        'status': 'active',
        'direction': 'pull',
      });
      expect(connection.serverSide, isTrue);
    });

    test('a non-server-side connector is carried through', () {
      final obsidian = Connection.fromJson({
        'id': '018f',
        'provider': 'obsidian',
        'label': 'Coffre',
        'status': 'active',
        'direction': 'push',
        'server_side': false,
      });
      expect(obsidian.serverSide, isFalse);
    });

    test('direction never defaults to writing into somebody\'s calendar', () {
      final connection = Connection.fromJson({
        'id': '018f',
        'provider': 'google_calendar',
        'label': 'Agenda',
        'status': 'active',
      });
      expect(connection.direction, SyncDirection.pull);
    });
  });

  group('SyncReport', () {
    test('a provider outage is a 200 with failed, not an exception', () {
      final report = SyncReport.fromJson({
        'provider': 'slack',
        'failed': true,
        'reason': 'service indisponible',
      });
      expect(report.failed, isTrue);
      expect(report.reason, 'service indisponible');
      expect(report.changed, 0);
    });

    test('counts what actually changed', () {
      final report = SyncReport.fromJson({
        'provider': 'google_calendar',
        'created': 2,
        'updated': 3,
        'unchanged': 40,
        'deleted': 1,
        'conflicts': 1,
      });
      // `unchanged` is deliberately excluded: "45 éléments synchronisés" when
      // forty of them did nothing overstates what happened.
      expect(report.changed, 6);
    });
  });

  group('OperationalHealth', () {
    test('a partition gap makes the account unhealthy on its own', () {
      final health = OperationalHealth.fromJson({
        'embedding_backlog': 0,
        'failing_integrations': <String>[],
        'audit_partitions': 12,
        'audit_partition_gap': true,
      });
      expect(health.healthy, isFalse);
    });

    test('nothing wrong reads as healthy', () {
      final health = OperationalHealth.fromJson({
        'audit_partitions': 12,
        'audit_partition_gap': false,
      });
      expect(health.healthy, isTrue);
    });
  });

  group('AuditEntry', () {
    test('translates the actions it knows', () {
      final entry = AuditEntry.fromJson({
        'id': 4821,
        'action': 'workspace.member.added',
        'actor_type': 'user',
      });
      expect(entry.label, 'Membre ajouté à un espace');
    });

    test('shows the raw action rather than inventing a sentence', () {
      // A wrong French label in an audit trail is worse than an untranslated
      // one: the reader cannot tell it is wrong.
      final entry = AuditEntry.fromJson({
        'id': 1,
        'action': 'something.new',
        'actor_type': 'system',
      });
      expect(entry.label, 'something.new');
    });
  });
}
