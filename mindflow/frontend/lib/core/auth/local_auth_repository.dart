/// Development-only identity, for running the app against the local stack
/// without a Supabase project.
///
/// It mints the same unsigned token the backend's `make_local_token` produces.
/// That token is **rejected outright** in staging and production: `Settings`
/// refuses to start there unless a real verification method is configured, and
/// `TokenVerifier` only skips signature checks when the environment is `local`
/// or `test`. So the worst this can do is fail to authenticate.
///
/// Enabled only by an explicit build flag:
///
///     flutter run --dart-define=MINDFLOW_LOCAL_AUTH=true
library;

import 'dart:async';
import 'dart:convert';

import 'auth_repository.dart';

const kLocalAuthEnabled = bool.fromEnvironment('MINDFLOW_LOCAL_AUTH');

class LocalAuthRepository implements AuthRepository {
  final _changes = StreamController<AppUser?>.broadcast();
  AppUser? _user;

  @override
  AppUser? get currentUser => _user;

  @override
  Stream<AppUser?> userChanges() async* {
    yield _user;
    yield* _changes.stream;
  }

  @override
  Future<String?> accessToken() async {
    final user = _user;
    if (user == null) return null;
    return unsignedToken(subject: user.id, email: user.email ?? '');
  }

  @override
  Future<void> signIn({required String email, required String password}) async {
    final address = email.trim().toLowerCase();
    if (address.isEmpty) throw const AuthFailure('Adresse e-mail requise.');
    // A stable id per address, so restarting the app keeps the same account.
    _user = AppUser(id: stableUuidFrom(address), email: email.trim());
    _changes.add(_user);
  }

  @override
  Future<void> signUp({required String email, required String password}) =>
      signIn(email: email, password: password);

  @override
  Future<void> signOut() async {
    _user = null;
    _changes.add(null);
  }

  void dispose() => _changes.close();
}

/// Deterministic RFC 4122-shaped id derived from the address. Not a real UUIDv5
/// — it only has to be stable across restarts and well formed enough for the
/// server to parse.
String stableUuidFrom(String seed) {
  final bytes = utf8.encode(seed);
  var hash = 0x811c9dc5;
  final digest = <int>[];
  for (var i = 0; i < 16; i++) {
    for (final byte in bytes) {
      hash = ((hash ^ (byte + i)) * 0x01000193) & 0xFFFFFFFF;
    }
    digest.add(hash & 0xFF);
  }
  digest[6] = (digest[6] & 0x0F) | 0x40;
  digest[8] = (digest[8] & 0x3F) | 0x80;
  final hex =
      digest.map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}'
      '-${hex.substring(16, 20)}-${hex.substring(20, 32)}';
}

String _segment(Object value) =>
    base64Url.encode(utf8.encode(jsonEncode(value))).replaceAll('=', '');

String unsignedToken({required String subject, required String email}) {
  final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final header = _segment({'alg': 'HS256', 'typ': 'JWT'});
  final payload = _segment({
    'sub': subject,
    'email': email,
    'role': 'authenticated',
    'aud': 'authenticated',
    'iat': now,
    'exp': now + 3600,
  });
  // No valid signature exists for a secret this app does not have; the local
  // backend does not check one.
  final signature =
      base64Url.encode(utf8.encode('local-development')).replaceAll('=', '');
  return '$header.$payload.$signature';
}
