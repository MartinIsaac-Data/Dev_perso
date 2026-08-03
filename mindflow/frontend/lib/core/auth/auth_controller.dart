/// Auth state exposed to the widget tree.
///
/// Two providers, on purpose:
///
/// * [authUserProvider] is the *fact* — who is signed in. The router reads it.
/// * [signInControllerProvider] is the *action* — the state of the form the user
///   is currently submitting. Screens read it.
///
/// Merging them would make the router rebuild on every keystroke of a failed
/// password attempt.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth_repository.dart';

/// `AsyncLoading` here means "we do not know yet" — the very first frame, before
/// Supabase has restored the persisted session. The router must show a splash
/// during that window instead of bouncing the user to the login screen.
final authUserProvider = StreamProvider<AppUser?>((ref) {
  final repository = ref.watch(authRepositoryProvider);
  return repository.userChanges();
});

/// Synchronous best-effort read, used where an async gap would be awkward.
final currentUserProvider = Provider<AppUser?>((ref) {
  return ref.watch(authUserProvider).maybeWhen(
        data: (user) => user,
        orElse: () => ref.watch(authRepositoryProvider).currentUser,
      );
});

enum AuthMode { signIn, signUp }

class SignInController extends StateNotifier<AsyncValue<void>> {
  SignInController(this._repository) : super(const AsyncValue.data(null));

  final AuthRepository _repository;

  Future<bool> submit({
    required AuthMode mode,
    required String email,
    required String password,
  }) async {
    state = const AsyncValue.loading();
    try {
      if (mode == AuthMode.signIn) {
        await _repository.signIn(email: email, password: password);
      } else {
        await _repository.signUp(email: email, password: password);
      }
      // Do not reset to `data` on success: the router is about to unmount this
      // screen, and setting state on a disposed notifier throws.
      if (mounted) state = const AsyncValue.data(null);
      return true;
    } on AuthFailure catch (error, stack) {
      if (mounted) state = AsyncValue.error(error, stack);
      return false;
    } catch (error, stack) {
      if (mounted) {
        state = AsyncValue.error(
          const AuthFailure('Connexion impossible. Vérifiez votre réseau.'),
          stack,
        );
      }
      return false;
    }
  }

  Future<void> signOut() => _repository.signOut();
}

final signInControllerProvider =
    StateNotifierProvider.autoDispose<SignInController, AsyncValue<void>>(
        (ref) {
  return SignInController(ref.watch(authRepositoryProvider));
});
