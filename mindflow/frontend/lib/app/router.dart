/// Navigation.
///
/// The redirect is the only place that decides whether a screen is reachable.
/// Guarding inside each screen instead would mean every new screen is a chance
/// to forget the check.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/auth/auth_controller.dart';
import '../features/auth/login_screen.dart';
import '../features/capture/capture_detail_screen.dart';
import '../features/capture/record_screen.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/notes/note_detail_screen.dart';
import '../features/notes/notes_screen.dart';

class Routes {
  static const login = '/login';
  static const dashboard = '/';
  static const notes = '/notes';
  static const record = '/record';

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

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _AuthRefresh(ref);
  ref.onDispose(refresh.dispose);

  return GoRouter(
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
      GoRoute(
          path: Routes.dashboard, builder: (_, __) => const DashboardScreen()),
      GoRoute(path: Routes.notes, builder: (_, __) => const NotesScreen()),
      GoRoute(
        path: '/notes/:id',
        builder: (_, state) =>
            NoteDetailScreen(entryId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: Routes.record,
        builder: (_, __) => const RecordScreen(),
      ),
      GoRoute(
        path: '/captures/:id',
        builder: (_, state) =>
            CaptureDetailScreen(captureId: state.pathParameters['id']!),
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
