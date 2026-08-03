/// Identity, delegated to Supabase Auth (ADR-029).
///
/// The app never mints or validates a token itself: it obtains one from Supabase
/// and forwards it to the MindFlow API, which verifies the signature. That is
/// why this file is deliberately thin — every line of custom auth logic here
/// would be a line the backend cannot trust.
///
/// The interface is abstract so tests (and a future migration away from
/// Supabase) do not depend on the SDK's own types.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart' as supabase;

/// What the rest of the app is allowed to know about a session.
class AppUser {
  const AppUser({required this.id, required this.email});

  final String id;
  final String? email;
}

class AuthFailure implements Exception {
  const AuthFailure(this.message);
  final String message;

  @override
  String toString() => message;
}

abstract class AuthRepository {
  /// Emits on sign-in, sign-out and token refresh. `null` means signed out.
  Stream<AppUser?> userChanges();

  AppUser? get currentUser;

  /// The access token to attach to API calls, refreshed if it is about to
  /// expire. Returns null when signed out.
  Future<String?> accessToken();

  Future<void> signIn({required String email, required String password});

  Future<void> signUp({required String email, required String password});

  Future<void> signOut();
}

class SupabaseAuthRepository implements AuthRepository {
  SupabaseAuthRepository(this._auth);

  final supabase.GoTrueClient _auth;

  /// Refresh a little before the token actually expires. Without this margin a
  /// request started at T-1s can still arrive expired, and the user sees a
  /// spurious sign-out.
  static const _refreshMargin = Duration(seconds: 60);

  @override
  AppUser? get currentUser => _map(_auth.currentUser);

  @override
  Stream<AppUser?> userChanges() =>
      _auth.onAuthStateChange.map((event) => _map(event.session?.user));

  @override
  Future<String?> accessToken() async {
    final session = _auth.currentSession;
    if (session == null) return null;

    final expiresAt = session.expiresAt;
    if (expiresAt != null) {
      final expiry =
          DateTime.fromMillisecondsSinceEpoch(expiresAt * 1000, isUtc: true);
      if (expiry.subtract(_refreshMargin).isBefore(DateTime.now().toUtc())) {
        try {
          final refreshed = await _auth.refreshSession();
          return refreshed.session?.accessToken;
        } on supabase.AuthException {
          // The refresh token is dead: the caller will get a 401 and the app
          // will route back to login. Swallowing here avoids two error paths
          // for the same fact.
          return null;
        }
      }
    }
    return session.accessToken;
  }

  @override
  Future<void> signIn({required String email, required String password}) async {
    try {
      await _auth.signInWithPassword(email: email.trim(), password: password);
    } on supabase.AuthException catch (error) {
      throw AuthFailure(_readable(error));
    }
  }

  @override
  Future<void> signUp({required String email, required String password}) async {
    try {
      await _auth.signUp(email: email.trim(), password: password);
    } on supabase.AuthException catch (error) {
      throw AuthFailure(_readable(error));
    }
  }

  @override
  Future<void> signOut() => _auth.signOut();

  AppUser? _map(supabase.User? user) =>
      user == null ? null : AppUser(id: user.id, email: user.email);

  /// Supabase messages are in English and occasionally cryptic. The credential
  /// case stays deliberately vague: distinguishing "unknown email" from "wrong
  /// password" hands an attacker a user enumeration oracle.
  String _readable(supabase.AuthException error) {
    final message = error.message.toLowerCase();
    if (message.contains('invalid login credentials')) {
      return 'Identifiants incorrects.';
    }
    if (message.contains('email not confirmed')) {
      return 'Adresse e-mail non confirmée. Vérifiez votre boîte de réception.';
    }
    if (message.contains('already registered') ||
        message.contains('already exists')) {
      return 'Un compte existe déjà pour cette adresse.';
    }
    if (message.contains('password')) {
      return 'Mot de passe trop faible : 8 caractères minimum.';
    }
    if (message.contains('rate limit') || message.contains('too many')) {
      return 'Trop de tentatives. Réessayez dans quelques minutes.';
    }
    return 'Connexion impossible. Réessayez dans un instant.';
  }
}

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return SupabaseAuthRepository(supabase.Supabase.instance.client.auth);
});
