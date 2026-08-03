import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/auth/auth_repository.dart';
import 'package:mindflow/features/auth/login_screen.dart';

class FakeAuthRepository implements AuthRepository {
  FakeAuthRepository({this.failure});

  final AuthFailure? failure;
  final _changes = StreamController<AppUser?>.broadcast();

  AppUser? _user;
  int signInCalls = 0;
  int signUpCalls = 0;
  String? lastEmail;

  @override
  AppUser? get currentUser => _user;

  @override
  Stream<AppUser?> userChanges() async* {
    yield _user;
    yield* _changes.stream;
  }

  @override
  Future<String?> accessToken() async => _user == null ? null : 'token';

  @override
  Future<void> signIn({required String email, required String password}) async {
    signInCalls += 1;
    lastEmail = email;
    final error = failure;
    if (error != null) throw error;
    _user = AppUser(id: 'u1', email: email);
    _changes.add(_user);
  }

  @override
  Future<void> signUp({required String email, required String password}) async {
    signUpCalls += 1;
    lastEmail = email;
    final error = failure;
    if (error != null) throw error;
    _user = AppUser(id: 'u1', email: email);
    _changes.add(_user);
  }

  @override
  Future<void> signOut() async {
    _user = null;
    _changes.add(null);
  }

  void dispose() => _changes.close();
}

void main() {
  late FakeAuthRepository auth;

  Widget harness(FakeAuthRepository repository) => ProviderScope(
        overrides: [authRepositoryProvider.overrideWithValue(repository)],
        child: const MaterialApp(home: LoginScreen()),
      );

  tearDown(() => auth.dispose());

  testWidgets('refuses to submit an empty form', (tester) async {
    auth = FakeAuthRepository();
    await tester.pumpWidget(harness(auth));

    await tester.tap(find.byKey(const Key('login_submit')));
    await tester.pump();

    expect(find.text('Adresse e-mail requise.'), findsOneWidget);
    expect(find.text('Mot de passe requis.'), findsOneWidget);
    expect(auth.signInCalls, 0);
  });

  testWidgets('rejects a malformed address before calling the server',
      (tester) async {
    auth = FakeAuthRepository();
    await tester.pumpWidget(harness(auth));

    await tester.enterText(find.byKey(const Key('login_email')), 'jean');
    await tester.enterText(
        find.byKey(const Key('login_password')), 'motdepasse');
    await tester.tap(find.byKey(const Key('login_submit')));
    await tester.pump();

    expect(find.text('Adresse e-mail invalide.'), findsOneWidget);
    expect(auth.signInCalls, 0);
  });

  testWidgets('signs in with valid credentials', (tester) async {
    auth = FakeAuthRepository();
    await tester.pumpWidget(harness(auth));

    await tester.enterText(
        find.byKey(const Key('login_email')), 'jean@exemple.fr');
    await tester.enterText(
        find.byKey(const Key('login_password')), 'motdepasse');
    await tester.tap(find.byKey(const Key('login_submit')));
    await tester.pumpAndSettle();

    expect(auth.signInCalls, 1);
    expect(auth.lastEmail, 'jean@exemple.fr');
  });

  testWidgets('shows the failure message without clearing the form',
      (tester) async {
    auth = FakeAuthRepository(
        failure: const AuthFailure('Identifiants incorrects.'));
    await tester.pumpWidget(harness(auth));

    await tester.enterText(
        find.byKey(const Key('login_email')), 'jean@exemple.fr');
    await tester.enterText(find.byKey(const Key('login_password')), 'faux');
    await tester.tap(find.byKey(const Key('login_submit')));
    await tester.pumpAndSettle();

    expect(find.text('Identifiants incorrects.'), findsOneWidget);
    // Retyping an address after a failed attempt is the fastest way to make
    // someone give up.
    expect(find.text('jean@exemple.fr'), findsOneWidget);
  });

  testWidgets('enforces a password floor on sign-up only', (tester) async {
    auth = FakeAuthRepository();
    await tester.pumpWidget(harness(auth));

    await tester.tap(find.text('Pas encore de compte ? Créer un compte'));
    await tester.pump();

    await tester.enterText(
        find.byKey(const Key('login_email')), 'jean@exemple.fr');
    await tester.enterText(find.byKey(const Key('login_password')), 'court');
    await tester.tap(find.byKey(const Key('login_submit')));
    await tester.pump();

    expect(find.text('8 caractères minimum.'), findsOneWidget);
    expect(auth.signUpCalls, 0);
  });
}
