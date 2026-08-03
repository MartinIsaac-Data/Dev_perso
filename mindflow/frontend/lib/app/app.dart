import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:go_router/go_router.dart';

import '../core/api/planning_models.dart';
import '../core/design/theme.dart';
import '../features/planning/planning_providers.dart';
import 'router.dart';

/// Opens whatever the command palette selected.
///
/// Lives here rather than in the palette so that widget stays free of route
/// knowledge — it is a list, not a navigator.
void openQuickHit(BuildContext context, QuickHit hit) {
  // The container rather than a `WidgetRef`: this is invoked from the palette's
  // row callback, which has a context but no ref of its own.
  final container = ProviderScope.containerOf(context, listen: false);
  switch (hit.kind) {
    case 'entry':
      context.push(Routes.note(hit.id));
    case 'capture':
      context.push(Routes.capture(hit.id));
    case 'project':
      container.read(searchQueryProvider.notifier).state =
          '@${hit.title.toLowerCase()}';
      context.go(Routes.search);
    case 'tag':
      container.read(searchQueryProvider.notifier).state = hit.title;
      context.go(Routes.search);
  }
}

class MindflowApp extends ConsumerWidget {
  const MindflowApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'MindFlow AI',
      debugShowCheckedModeBanner: false,
      routerConfig: ref.watch(routerProvider),
      theme: buildAppTheme(Brightness.light),
      darkTheme: buildAppTheme(Brightness.dark),
      // The product speaks French; dates, relative times and pluralisation must
      // follow, otherwise "in 2 days" leaks through in a French sentence.
      locale: const Locale('fr', 'FR'),
      supportedLocales: const [Locale('fr', 'FR'), Locale('en', 'US')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
    );
  }
}

/// Shown while Supabase restores the persisted session, and whenever a screen
/// is waiting on its first payload.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}

/// Configuration is missing at build time. Better a screen that says exactly
/// what to pass than a stack trace at startup.
class ConfigurationErrorApp extends StatelessWidget {
  const ConfigurationErrorApp({required this.message, super.key});

  final String message;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(Brightness.light),
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.settings_outlined, size: 40),
                const SizedBox(height: 16),
                Text(
                  'Configuration incomplète',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                Text(message),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
