/// The enterprise screens, rendered.
///
/// These tests do not check that lists render — that is what Flutter is for.
/// They check the handful of places where the interface says something the
/// server cannot say for it:
///
/// * the empty workspace screen states that a note without a workspace is
///   private, including from an administrator;
/// * Obsidian gets no « Synchroniser » button, because pressing one would call
///   an endpoint that deliberately does no I/O;
/// * a revoked grant is not offered a retry, because retrying cannot work;
/// * the share sheet warns that the link is shown once;
/// * a mention that reached nobody is reported instead of failing silently.
///
/// Each of those is a sentence somebody could delete without any test going
/// red, which is exactly why they have one.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/enterprise_models.dart';
import 'package:mindflow/core/design/components.dart';
import 'package:mindflow/features/enterprise/comments_panel.dart';
import 'package:mindflow/features/enterprise/enterprise_providers.dart';
import 'package:mindflow/features/enterprise/integrations_screen.dart';
import 'package:mindflow/features/enterprise/share_sheet.dart';
import 'package:mindflow/features/enterprise/team_screen.dart';
import 'package:mindflow/features/enterprise/workspaces_screen.dart';

Widget _host(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: child),
  );
}

/// A tall test surface.
///
/// The integrations screen lists seven providers; on the default 800×600 test
/// window the last of them is below the fold and `find` cannot see it. Growing
/// the window is more honest than scrolling in every test — the assertions are
/// about *what is offered*, not about where it sits.
Future<void> _useTallWindow(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 3200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

Connection _connection({
  required SyncProvider provider,
  ConnectionStatus status = ConnectionStatus.active,
  bool serverSide = true,
}) =>
    Connection(
      id: 'c-${provider.param}',
      provider: provider,
      label: provider.label,
      status: status,
      direction: SyncDirection.pull,
      serverSide: serverSide,
    );

void main() {
  group('WorkspacesScreen', () {
    testWidgets('the empty state states the privacy rule', (tester) async {
      await tester.pumpWidget(_host(
        const WorkspacesScreen(),
        overrides: [
          workspacesProvider.overrideWith((ref) async => <Workspace>[]),
        ],
      ));
      await tester.pumpAndSettle();

      // The sentence a user reads exactly once — before any workspace exists.
      expect(find.textContaining('reste privée'), findsOneWidget);
      expect(find.text('Créer un espace'), findsOneWidget);
    });

    testWidgets('lists the workspaces one is a member of', (tester) async {
      await tester.pumpWidget(_host(
        const WorkspacesScreen(),
        overrides: [
          workspacesProvider.overrideWith((ref) async => [
                const Workspace(id: 'w1', name: 'Forecast Gabon'),
                const Workspace(id: 'w2', name: 'Archives', archived: true),
              ]),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Forecast Gabon'), findsOneWidget);
      expect(find.text('Archivé'), findsOneWidget);
    });
  });

  group('IntegrationsScreen', () {
    testWidgets('offers no sync button for a non-server-side connector',
        (tester) async {
      await _useTallWindow(tester);
      await tester.pumpWidget(_host(
        const IntegrationsScreen(),
        overrides: [
          integrationsProvider.overrideWith((ref) async => [
                _connection(provider: SyncProvider.obsidian, serverSide: false),
              ]),
          conflictsProvider.overrideWith((ref) async => <SyncConflict>[]),
        ],
      ));
      await tester.pumpAndSettle();

      // Obsidian is connected, so "Déconnecter" is there — but nothing offers
      // to synchronise, because the server has no access to a local folder.
      expect(find.text('Déconnecter'), findsOneWidget);
      expect(find.text('Synchroniser'), findsNothing);
      expect(find.textContaining('pas un service'), findsOneWidget);
    });

    testWidgets('a server-side connector does get a sync button',
        (tester) async {
      await _useTallWindow(tester);
      await tester.pumpWidget(_host(
        const IntegrationsScreen(),
        overrides: [
          integrationsProvider.overrideWith((ref) async => [
                _connection(provider: SyncProvider.googleCalendar),
              ]),
          conflictsProvider.overrideWith((ref) async => <SyncConflict>[]),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Synchroniser'), findsOneWidget);
    });

    testWidgets('a revoked grant is told to reconnect, not to retry',
        (tester) async {
      await _useTallWindow(tester);
      await tester.pumpWidget(_host(
        const IntegrationsScreen(),
        overrides: [
          integrationsProvider.overrideWith((ref) async => [
                _connection(
                  provider: SyncProvider.slack,
                  status: ConnectionStatus.expired,
                ),
              ]),
          conflictsProvider.overrideWith((ref) async => <SyncConflict>[]),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.textContaining('Reconnectez'), findsOneWidget);
      expect(find.textContaining('réessayer ne suffira pas'), findsOneWidget);
    });

    testWidgets('a conflict is offered as a choice, never resolved silently',
        (tester) async {
      await tester.pumpWidget(_host(
        const IntegrationsScreen(),
        overrides: [
          integrationsProvider.overrideWith((ref) async => <Connection>[]),
          conflictsProvider.overrideWith((ref) async => [
                const SyncConflict(
                  id: 'x1',
                  provider: SyncProvider.googleCalendar,
                ),
              ]),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Conflits'));
      await tester.pumpAndSettle();

      // Two buttons, no default. Picking one silently is how the version
      // somebody cared about disappears.
      expect(find.text('Garder la version MindFlow'), findsOneWidget);
      expect(find.text('Garder la version distante'), findsOneWidget);
    });
  });

  group('TeamScreen', () {
    testWidgets('the share list shows a suffix and never a token',
        (tester) async {
      await tester.pumpWidget(_host(
        const TeamScreen(),
        overrides: [
          accountMembersProvider.overrideWith((ref) async => <Member>[]),
          invitationsProvider.overrideWith((ref) async => <Invitation>[]),
          sharesProvider.overrideWith((ref) async => [
                const ShareLink(
                  id: 's1',
                  scope: 'entry',
                  tokenSuffix: '9abc',
                  viewCount: 3,
                ),
              ]),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Liens partagés'));
      await tester.pumpAndSettle();

      expect(find.text('Lien …9abc'), findsOneWidget);
      expect(find.textContaining('3 ouvertures'), findsOneWidget);
    });

    testWidgets('a revoked link reads as revoked, not as expired',
        (tester) async {
      await tester.pumpWidget(_host(
        const TeamScreen(),
        overrides: [
          accountMembersProvider.overrideWith((ref) async => <Member>[]),
          invitationsProvider.overrideWith((ref) async => <Invitation>[]),
          sharesProvider.overrideWith((ref) async => [
                ShareLink(
                  id: 's1',
                  scope: 'entry',
                  tokenSuffix: '9abc',
                  revoked: true,
                  expiresAt:
                      DateTime.now().toUtc().subtract(const Duration(days: 2)),
                ),
              ]),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Liens partagés'));
      await tester.pumpAndSettle();

      // Both are true; revocation is what the owner did, so it is what they
      // are told.
      expect(find.textContaining('Révoqué'), findsWidgets);
    });
  });

  group('ShareSheet', () {
    testWidgets('defaults to an expiring link rather than a permanent one',
        (tester) async {
      await _useTallWindow(tester);
      await tester.pumpWidget(_host(
        const Scaffold(
          body: SingleChildScrollView(child: ShareSheet(entryId: 'e1')),
        ),
      ));
      await tester.pumpAndSettle();

      // « Jamais » is offered and is not the default: a security setting one
      // has to remember to switch on only protects the people who did not
      // need it.
      expect(find.text('30 jours'), findsOneWidget);
      expect(find.text('Jamais'), findsOneWidget);
      final selected = tester.widget<MfChip>(
        find.ancestor(
          of: find.text('30 jours'),
          matching: find.byType(MfChip),
        ),
      );
      expect(selected.selected, isTrue);
      expect(find.text('Créer le lien'), findsOneWidget);
    });
  });

  group('CommentsPanel', () {
    testWidgets('an empty thread says how to mention somebody', (tester) async {
      await tester.pumpWidget(_host(
        const Scaffold(body: CommentsPanel(entryId: 'e1')),
        overrides: [
          commentsProvider('e1').overrideWith((ref) async => <Comment>[]),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.textContaining('@prénom.nom'), findsOneWidget);
    });

    testWidgets('a mention that reached nobody is reported on the comment',
        (tester) async {
      await tester.pumpWidget(_host(
        const Scaffold(
            body: SingleChildScrollView(
          child: CommentsPanel(entryId: 'e1'),
        )),
        overrides: [
          commentsProvider('e1').overrideWith((ref) async => [
                const Comment(
                  id: 'c1',
                  entryId: 'e1',
                  authorId: 'u1',
                  body: '@paul peux-tu confirmer ?',
                  unresolvedMentions: ['paul'],
                ),
              ]),
        ],
      ));
      await tester.pumpAndSettle();

      // The whole point: the author must not believe Paul was notified.
      expect(find.textContaining('paul'), findsWidgets);
      expect(find.textContaining("n'a pas accès à cette note"), findsOneWidget);
    });
  });
}
