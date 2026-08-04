import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'app/app.dart';
import 'core/design/command_palette.dart';
import 'core/api/client.dart';
import 'core/auth/auth_controller.dart';
import 'core/auth/auth_repository.dart';
import 'core/auth/local_auth_repository.dart';
import 'core/notifications/notification_bootstrap.dart';
import 'core/storage/boot_screen.dart';
import 'core/time/device_timezone.dart';

/// Supabase project credentials, injected at build time. The anon key is a
/// public identifier, not a secret — every mobile client carries it, and Row
/// Level Security is what actually protects the data.
const kSupabaseUrl = String.fromEnvironment('SUPABASE_URL');
const kSupabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('fr_FR');
  // The timezone database has to be loaded before any local notification can be
  // scheduled: `zonedSchedule` needs a `TZDateTime`, and a toast scheduled in
  // the wrong zone fires at the wrong hour, which is worse than not firing.
  await initialiseNotificationTimezone();

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
        // The palette needs to open things; the router lives in `app/`. Injected
        // here so neither has to import the other.
        paletteNavigationProvider.overrideWithValue(openQuickHit),
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
      // The first frame is up, so the placeholder in `web/index.html` has done
      // its job. Nothing removes it on its own — the engine appends its view
      // and leaves the rest of the document alone.
      dismissBootScreen();
      unawaited(ref.read(deviceTimezoneProvider).refresh());
    });

    // Device registration and the local reminder mirror both need a signed-in
    // user, so they wait for one rather than running at startup.
    ref.listenManual(authUserProvider, (previous, next) {
      if (next.valueOrNull != null && previous?.valueOrNull == null) {
        unawaited(bootstrapNotifications(ref));
      }
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
