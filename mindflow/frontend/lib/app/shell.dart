/// The application shell.
///
/// Adaptive rather than responsive-by-breakpoint-only: on a wide window a
/// Linear-style sidebar, on a narrow one a bottom bar with the four
/// destinations that matter on a phone. The remaining screens are reachable from
/// the command palette, which is precisely why adding a screen in phase 2 did
/// not require adding a tab.
///
/// ⌘K / Ctrl-K is bound at this level so it works from every screen, including
/// ones that have their own text fields.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/api/planning_models.dart';
import '../core/design/command_palette.dart';
import '../core/design/components.dart';
import '../core/design/tokens.dart';
import '../features/planning/planning_providers.dart';
import 'router.dart';

/// A shell destination. Order is deliberate: capture is not in this list because
/// it is a *verb*, and verbs belong on a button, not in navigation.
class ShellDestination {
  const ShellDestination({
    required this.label,
    required this.icon,
    required this.selectedIcon,
    required this.route,
    this.compact = true,
  });

  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final String route;

  /// Whether it appears in the phone's bottom bar. Five is the practical
  /// ceiling; past that the labels truncate and nobody reads them.
  final bool compact;
}

const shellDestinations = <ShellDestination>[
  ShellDestination(
    label: 'Accueil',
    icon: Icons.home_outlined,
    selectedIcon: Icons.home,
    route: Routes.dashboard,
  ),
  ShellDestination(
    label: 'Agenda',
    icon: Icons.calendar_today_outlined,
    selectedIcon: Icons.calendar_today,
    route: Routes.agenda,
  ),
  ShellDestination(
    label: 'Notes',
    icon: Icons.subject_outlined,
    selectedIcon: Icons.subject,
    route: Routes.notes,
  ),
  ShellDestination(
    label: 'Notifications',
    icon: Icons.notifications_none,
    selectedIcon: Icons.notifications,
    route: Routes.notifications,
  ),
  ShellDestination(
    label: 'Calendrier',
    icon: Icons.calendar_month_outlined,
    selectedIcon: Icons.calendar_month,
    route: Routes.calendar,
    compact: false,
  ),
  ShellDestination(
    label: 'Recherche',
    icon: Icons.search,
    selectedIcon: Icons.search,
    route: Routes.search,
    compact: false,
  ),
  ShellDestination(
    label: 'Statistiques',
    icon: Icons.insights_outlined,
    selectedIcon: Icons.insights,
    route: Routes.analytics,
    compact: false,
  ),
  ShellDestination(
    label: 'Historique',
    icon: Icons.history,
    selectedIcon: Icons.history,
    route: Routes.timeline,
    compact: false,
  ),
];

class AppShell extends ConsumerStatefulWidget {
  const AppShell({required this.child, required this.location, super.key});

  final Widget child;
  final String location;

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _registerPalette());
  }

  /// Commands are registered from the shell so the palette itself stays free of
  /// route knowledge — it is a widget, not a navigator.
  void _registerPalette() {
    if (!mounted) return;
    ref.read(paletteActionsProvider.notifier).state = [
      PaletteAction(
        id: 'capture',
        label: 'Capturer une note vocale',
        icon: Icons.mic,
        keywords: const ['enregistrer', 'voix', 'micro', 'dicter'],
        shortcut: const ['⌘', 'N'],
        onInvoke: (context, _) => context.push(Routes.record),
      ),
      PaletteAction(
        id: 'agenda',
        label: 'Agenda',
        icon: Icons.calendar_today_outlined,
        keywords: const ['échéances', 'semaine', 'planning'],
        onInvoke: (context, _) => context.go(Routes.agenda),
      ),
      PaletteAction(
        id: 'calendar',
        label: 'Calendrier',
        icon: Icons.calendar_month_outlined,
        keywords: const ['mois', 'grille'],
        onInvoke: (context, _) => context.go(Routes.calendar),
      ),
      PaletteAction(
        id: 'today',
        label: "Aujourd'hui",
        icon: Icons.today_outlined,
        keywords: const ['jour', 'now'],
        onInvoke: (context, ref) {
          ref.read(agendaQueryProvider.notifier).state =
              AgendaQuery(view: AgendaView.day, anchor: DateTime.now());
          context.go(Routes.agenda);
        },
      ),
      PaletteAction(
        id: 'overdue',
        label: 'Tâches en retard',
        icon: Icons.error_outline,
        keywords: const ['retard', 'overdue', 'dépassées'],
        onInvoke: (context, ref) {
          ref.read(searchQueryProvider.notifier).state = 'is:task is:overdue';
          context.go(Routes.search);
        },
      ),
      PaletteAction(
        id: 'review',
        label: 'Éléments à vérifier',
        icon: Icons.help_outline,
        keywords: const ['review', 'confirmer', 'douteux'],
        onInvoke: (context, ref) {
          ref.read(searchQueryProvider.notifier).state = 'is:review';
          context.go(Routes.search);
        },
      ),
      PaletteAction(
        id: 'search',
        label: 'Rechercher',
        icon: Icons.search,
        keywords: const ['trouver', 'filtrer'],
        onInvoke: (context, _) => context.go(Routes.search),
      ),
      PaletteAction(
        id: 'stats',
        label: 'Statistiques',
        icon: Icons.insights_outlined,
        keywords: const ['analytics', 'tableau de bord', 'chiffres'],
        onInvoke: (context, _) => context.go(Routes.analytics),
      ),
      PaletteAction(
        id: 'timeline',
        label: 'Historique',
        icon: Icons.history,
        keywords: const ['activité', 'journal', 'timeline'],
        onInvoke: (context, _) => context.go(Routes.timeline),
      ),
      PaletteAction(
        id: 'notifications',
        label: 'Notifications',
        icon: Icons.notifications_none,
        keywords: const ['rappels', 'alertes'],
        onInvoke: (context, _) => context.go(Routes.notifications),
      ),
      PaletteAction(
        id: 'library',
        label: 'Projets et tags',
        icon: Icons.folder_outlined,
        keywords: const ['bibliothèque', 'organiser', 'étiquettes'],
        onInvoke: (context, _) => context.go(Routes.library),
      ),
    ];
  }

  int get _selectedIndex {
    final index = shellDestinations.indexWhere(
      (destination) => destination.route == Routes.dashboard
          ? widget.location == Routes.dashboard
          : widget.location.startsWith(destination.route),
    );
    return index < 0 ? 0 : index;
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final compact = width < Layout.compactMax;

    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyK, meta: true): () =>
            showCommandPalette(context, ref),
        const SingleActivator(LogicalKeyboardKey.keyK, control: true): () =>
            showCommandPalette(context, ref),
        const SingleActivator(LogicalKeyboardKey.keyN, meta: true): () =>
            context.push(Routes.record),
      },
      child: Focus(
        autofocus: true,
        child: compact
            ? _CompactShell(shell: widget)
            : _WideShell(shell: widget, selected: _selectedIndex),
      ),
    );
  }
}

class _WideShell extends ConsumerWidget {
  const _WideShell({required this.shell, required this.selected});

  final AppShell shell;
  final int selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: Row(
        children: [
          Container(
            width: Layout.sidebarWidth,
            decoration: BoxDecoration(
              color: scheme.surfaceContainerLow,
              border: Border(right: BorderSide(color: scheme.outlineVariant)),
            ),
            child: _Sidebar(location: shell.location),
          ),
          Expanded(child: shell.child),
        ],
      ),
    );
  }
}

class _Sidebar extends ConsumerWidget {
  const _Sidebar({required this.location});

  final String location;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    // Selects only the count: the sidebar must not rebuild when the whole
    // notification list changes.
    final unread = ref.watch(unreadCountProvider);

    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
                Space.lg, Space.lg, Space.lg, Space.md),
            child: Row(
              children: [
                Icon(Icons.graphic_eq,
                    size: 18, color: theme.colorScheme.primary),
                const SizedBox(width: Space.sm),
                Text('MindFlow', style: theme.textTheme.titleSmall),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.md),
            child: _PaletteButton(),
          ),
          const SizedBox(height: Space.md),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: Space.sm),
              children: [
                for (final destination in shellDestinations)
                  _SidebarTile(
                    destination: destination,
                    selected: destination.route == Routes.dashboard
                        ? location == Routes.dashboard
                        : location.startsWith(destination.route),
                    badge:
                        destination.route == Routes.notifications ? unread : 0,
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(Space.md),
            child: FilledButton.icon(
              onPressed: () => context.push(Routes.record),
              icon: const Icon(Icons.mic, size: 16),
              label: const Text('Capturer'),
            ),
          ),
        ],
      ),
    );
  }
}

class _PaletteButton extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return InkWell(
      onTap: () => showCommandPalette(context, ref),
      borderRadius: Radii.mdAll,
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: Space.md, vertical: Space.sm),
        decoration: BoxDecoration(
          color: scheme.surfaceContainer,
          borderRadius: Radii.mdAll,
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Row(
          children: [
            Icon(Icons.search, size: 14, color: scheme.onSurfaceVariant),
            const SizedBox(width: Space.sm),
            Expanded(
              child: Text('Rechercher…', style: theme.textTheme.labelMedium),
            ),
            const MfKeyHint(['⌘', 'K']),
          ],
        ),
      ),
    );
  }
}

class _SidebarTile extends StatelessWidget {
  const _SidebarTile({
    required this.destination,
    required this.selected,
    this.badge = 0,
  });

  final ShellDestination destination;
  final bool selected;
  final int badge;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 1),
      child: InkWell(
        onTap: () => context.go(destination.route),
        borderRadius: Radii.smAll,
        child: Container(
          height: Layout.compactRowHeight - 8,
          padding: const EdgeInsets.symmetric(horizontal: Space.md),
          decoration: BoxDecoration(
            color: selected ? scheme.surfaceContainerHigh : Colors.transparent,
            borderRadius: Radii.smAll,
          ),
          child: Row(
            children: [
              Icon(
                selected ? destination.selectedIcon : destination.icon,
                size: 16,
                color: selected ? scheme.primary : scheme.onSurfaceVariant,
              ),
              const SizedBox(width: Space.md),
              Expanded(
                child: Text(
                  destination.label,
                  style: theme.textTheme.labelLarge?.copyWith(
                    color:
                        selected ? scheme.onSurface : scheme.onSurfaceVariant,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                  ),
                ),
              ),
              if (badge > 0)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                  decoration: BoxDecoration(
                    color: scheme.primary,
                    borderRadius: Radii.pillAll,
                  ),
                  child: Text(
                    '$badge',
                    style: TextStyle(
                      fontSize: 10,
                      height: 1.4,
                      fontWeight: FontWeight.w700,
                      color: scheme.onPrimary,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CompactShell extends ConsumerWidget {
  const _CompactShell({required this.shell});

  final AppShell shell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final compactDestinations =
        shellDestinations.where((destination) => destination.compact).toList();
    final unread = ref.watch(unreadCountProvider);

    final index = compactDestinations.indexWhere(
      (destination) => destination.route == Routes.dashboard
          ? shell.location == Routes.dashboard
          : shell.location.startsWith(destination.route),
    );

    return Scaffold(
      body: shell.child,
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push(Routes.record),
        tooltip: 'Capturer',
        child: const Icon(Icons.mic),
      ),
      bottomNavigationBar: NavigationBar(
        height: 58,
        selectedIndex: index < 0 ? 0 : index,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        onDestinationSelected: (selected) =>
            context.go(compactDestinations[selected].route),
        destinations: [
          for (final destination in compactDestinations)
            NavigationDestination(
              icon: destination.route == Routes.notifications && unread > 0
                  ? Badge(label: Text('$unread'), child: Icon(destination.icon))
                  : Icon(destination.icon),
              selectedIcon: Icon(destination.selectedIcon),
              label: destination.label,
            ),
        ],
      ),
    );
  }
}
