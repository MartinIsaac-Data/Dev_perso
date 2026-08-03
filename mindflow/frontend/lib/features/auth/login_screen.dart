/// Sign in / sign up.
///
/// One form, two modes. A separate registration screen would double the surface
/// for a product whose entire onboarding is "say something out loud".
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/auth/auth_controller.dart';
import '../../core/auth/auth_repository.dart';
import '../../core/auth/local_auth_repository.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  AuthMode _mode = AuthMode.signIn;
  bool _obscured = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    // The router redirect handles navigation on success; nothing to do here.
    await ref.read(signInControllerProvider.notifier).submit(
          mode: _mode,
          email: _email.text,
          password: _password.text,
        );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(signInControllerProvider);
    final theme = Theme.of(context);
    final isSignIn = _mode == AuthMode.signIn;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Icon(Icons.graphic_eq,
                        size: 48, color: theme.colorScheme.primary),
                    const SizedBox(height: 20),
                    Text(
                      'MindFlow AI',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Dites-le. On s’occupe du reste.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                    const SizedBox(height: 32),
                    TextFormField(
                      key: const Key('login_email'),
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      autofillHints: const [AutofillHints.email],
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'Adresse e-mail',
                        prefixIcon: Icon(Icons.alternate_email),
                      ),
                      validator: (value) {
                        final email = (value ?? '').trim();
                        if (email.isEmpty) return 'Adresse e-mail requise.';
                        // Deliberately permissive: the only authority on whether
                        // an address exists is the confirmation e-mail.
                        if (!email.contains('@') || !email.contains('.')) {
                          return 'Adresse e-mail invalide.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      key: const Key('login_password'),
                      controller: _password,
                      obscureText: _obscured,
                      autofillHints: [
                        isSignIn
                            ? AutofillHints.password
                            : AutofillHints.newPassword,
                      ],
                      textInputAction: TextInputAction.done,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Mot de passe',
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          onPressed: () =>
                              setState(() => _obscured = !_obscured),
                          icon: Icon(
                            _obscured
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                          tooltip: _obscured ? 'Afficher' : 'Masquer',
                        ),
                      ),
                      validator: (value) {
                        final password = value ?? '';
                        if (password.isEmpty) return 'Mot de passe requis.';
                        if (!isSignIn && password.length < 8) {
                          return '8 caractères minimum.';
                        }
                        return null;
                      },
                    ),
                    if (state.hasError) ...[
                      const SizedBox(height: 16),
                      _ErrorBanner(
                        message: state.error is AuthFailure
                            ? (state.error! as AuthFailure).message
                            : 'Connexion impossible.',
                      ),
                    ],
                    const SizedBox(height: 24),
                    FilledButton(
                      key: const Key('login_submit'),
                      onPressed: state.isLoading ? null : _submit,
                      child: state.isLoading
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(
                              isSignIn ? 'Se connecter' : 'Créer mon compte'),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: state.isLoading
                          ? null
                          : () => setState(
                                () => _mode = isSignIn
                                    ? AuthMode.signUp
                                    : AuthMode.signIn,
                              ),
                      child: Text(
                        isSignIn
                            ? 'Pas encore de compte ? Créer un compte'
                            : 'J’ai déjà un compte',
                      ),
                    ),
                    if (kLocalAuthEnabled) ...[
                      const SizedBox(height: 16),
                      Text(
                        'Mode développement local : authentification simulée.',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.labelSmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: scheme.onErrorContainer, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child:
                Text(message, style: TextStyle(color: scheme.onErrorContainer)),
          ),
        ],
      ),
    );
  }
}
