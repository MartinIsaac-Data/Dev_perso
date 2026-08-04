/// Navigation.
///
/// The redirect is the only place that decides whether a screen is reachable.
/// Guarding inside each screen instead would mean every new screen is a chance
/// to forget the check — and phase 2 added eight.
///
/// Most routes sit inside a `ShellRoute`, so the sidebar and bottom bar persist
/// across navigation instead of being rebuilt per screen. The exceptions are the
/// full-screen flows: login, recording, and the detail pages pushed on top.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/auth/auth_controller.dart';
import '../features/auth/login_screen.dart';
import '../features/capture/capture_detail_screen.dart';
import '../features/capture/record_screen.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/enterprise/admin_screen.dart';
import '../features/enterprise/integrations_screen.dart';
import '../features/enterprise/mentions_screen.dart';
import '../features/enterprise/team_screen.dart';
import '../features/enterprise/workspaces_screen.dart';
import '../features/notes/note_detail_screen.dart';
import '../features/notes/notes_screen.dart';
import '../features/assistant/assistant_screen.dart';
import '../features/assistant/digests_screen.dart';
import '../features/assistant/knowledge_screen.dart';
import '../features/planning/agenda_screen.dart';
import '../features/planning/analytics_screen.dart';
import '../features/planning/calendar_screen.dart';
import '../features/planning/library_screen.dart';
import '../features/planning/notifications_screen.dart';
import '../features/planning/search_screen.dart';
import '../features/planning/timeline_screen.dart';
import 'shell.dart';

class Routes {
  static const login = '/login';
  static const dashboard = '/';
  static const notes = '/notes';
  static const record = '/record';

  // Phase 2
  static const agenda = '/agenda';
  static const calendar = '/calendar';
  static const search = '/search';
  static const analytics = '/stats';
  static const timeline = '/history';
  static const notifications = '/notifications';
  static const library = '/library';

  // Phase 3
  static const assistant = '/assistant';
  static const knowledge = '/knowledge';
  static const digests = '/digests';

  // Phase 4
  static const workspaces = '/workspaces';
  static const team = '/team';
  static const mentions = '/mentions';
  static const integrations = '/integrations';
  static const admin = '/admin';

  static String note(String id) => '/notes/$id';
  static String capture(String id) => '/captures/$id';
}

/// Bridges the auth stream to go_router, which wants a `Listenable`.
class _AuthRefresh extends ChangeNotifier {
  _AuthRefresh(this._ref) {
    _ref.listen(authUserProvider, (_, __) => notifyListeners());
  }

  // Held so the subscription lives as long as the router does.
  // ignore: unused_field
  final Ref _ref;
}

final _rootKey = GlobalKey<NavigatorState>();
final _shellKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _AuthRefresh(ref);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    navigatorKey: _rootKey,
    initialLocation: Routes.dashboard,
    refreshListenable: refresh,
    redirect: (context, state) {
      final auth = ref.read(authUserProvider);

      // First frames, before the persisted session has been restored. Sending
      // the user to /login here would flash a login screen at every cold start
      // for someone who is already signed in.
      if (auth.isLoading && !auth.hasValue) return null;

      final signedIn = auth.valueOrNull != null;
      final onLogin = state.matchedLocation == Routes.login;

      if (!signedIn) return onLogin ? null : Routes.login;
      if (onLogin) return Routes.dashboard;
      return null;
    },
    routes: [
      GoRoute(path: Routes.login, builder: (_, __) => const LoginScreen()),

      // Full-screen: recording takes the whole window on purpose — it has one
      // job and a navigation bar beside it would be an invitation to leave.
      GoRoute(
        path: Routes.record,
        parentNavigatorKey: _rootKey,
        builder: (_, __) => const RecordScreen(),
      ),
      GoRoute(
        path: '/notes/:id',
        parentNavigatorKey: _rootKey,
        builder: (_, state) =>
            NoteDetailScreen(entryId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/captures/:id',
        parentNavigatorKey: _rootKey,
        builder: (_, state) =>
            CaptureDetailScreen(captureId: state.pathParameters['id']!),
      ),

      ShellRoute(
        navigatorKey: _shellKey,
        builder: (context, state, child) =>
            AppShell(location: state.matchedLocation, child: child),
        routes: [
          GoRoute(
              path: Routes.dashboard,
              builder: (_, __) => const DashboardScreen()),
          GoRoute(path: Routes.notes, builder: (_, __) => const NotesScreen()),
          GoRoute(
              path: Routes.agenda, builder: (_, __) => const AgendaScreen()),
          GoRoute(
              path: Routes.calendar,
              builder: (_, __) => const CalendarScreen()),
          GoRoute(
            path: Routes.search,
            builder: (_, state) => SearchScreen(
              initialQuery: state.uri.queryParameters['q'],
            ),
          ),
          GoRoute(
              path: Routes.analytics,
              builder: (_, __) => const AnalyticsScreen()),
          GoRoute(
              path: Routes.assistant,
              builder: (_, __) => const AssistantScreen()),
          GoRoute(
              path: Routes.knowledge,
              builder: (_, __) => const KnowledgeScreen()),
          GoRoute(
              path: Routes.digests, builder: (_, __) => const DigestsScreen()),
          GoRoute(
              path: Routes.timeline,
              builder: (_, __) => const TimelineScreen()),
          GoRoute(
            path: Routes.notifications,
            builder: (_, __) => const NotificationsScreen(),
          ),
          GoRoute(
              path: Routes.library, builder: (_, __) => const LibraryScreen()),
          GoRoute(
              path: Routes.workspaces,
              builder: (_, __) => const WorkspacesScreen()),
          GoRoute(path: Routes.team, builder: (_, __) => const TeamScreen()),
          GoRoute(
              path: Routes.mentions,
              builder: (_, __) => const MentionsScreen()),
          GoRoute(
              path: Routes.integrations,
              builder: (_, __) => const IntegrationsScreen()),
          GoRoute(path: Routes.admin, builder: (_, __) => const AdminScreen()),
        ],
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      appBar: AppBar(title: const Text('Page introuvable')),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Aucun écran pour ${state.uri.path}'),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () => context.go(Routes.dashboard),
              child: const Text("Revenir à l'accueil"),
            ),
          ],
        ),
      ),
    ),
  );
});
