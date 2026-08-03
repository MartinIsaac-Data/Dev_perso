import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'app/app.dart';
import 'core/api/client.dart';
import 'core/auth/auth_repository.dart';
import 'core/auth/local_auth_repository.dart';
import 'core/time/device_timezone.dart';

/// Supabase project credentials, injected at build time. The anon key is a
/// public identifier, not a secret — every mobile client carries it, and Row
/// Level Security is what actually protects the data.
const kSupabaseUrl = String.fromEnvironment('SUPABASE_URL');
const kSupabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('fr_FR');

  if (!kLocalAuthEnabled) {
    if (kSupabaseUrl.isEmpty || kSupabaseAnonKey.isEmpty) {
      runApp(
        const ConfigurationErrorApp(
          message: 'Lancez avec --dart-define=SUPABASE_URL=… '
              '--dart-define=SUPABASE_ANON_KEY=…, ou en développement local '
              'avec --dart-define=MINDFLOW_LOCAL_AUTH=true.',
        ),
      );
      return;
    }
    // Supabase renamed the anon key to "publishable key"; the build flag
    // keeps its familiar name so existing run configurations keep working.
    await Supabase.initialize(
        url: kSupabaseUrl, publishableKey: kSupabaseAnonKey);
  }

  runApp(
    ProviderScope(
      overrides: [
        if (kLocalAuthEnabled)
          authRepositoryProvider.overrideWith((ref) {
            final repository = LocalAuthRepository();
            ref.onDispose(repository.dispose);
            return repository;
          }),
        // The API client asks the auth layer for a token on every request rather
        // than holding one: a token captured at construction time is a token
        // that expires while the app is backgrounded.
        apiProvider.overrideWith((ref) {
          final auth = ref.watch(authRepositoryProvider);
          return MindflowApi(tokenProvider: auth.accessToken);
        }),
      ],
      child: const _Bootstrap(child: MindflowApp()),
    ),
  );
}

/// Work that must happen once the container exists but before the first screen
/// needs it: resolving the device time zone and replaying anything the previous
/// session left queued.
class _Bootstrap extends ConsumerStatefulWidget {
  const _Bootstrap({required this.child});

  final Widget child;

  @override
  ConsumerState<_Bootstrap> createState() => _BootstrapState();
}

class _BootstrapState extends ConsumerState<_Bootstrap> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(ref.read(deviceTimezoneProvider).refresh());
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
