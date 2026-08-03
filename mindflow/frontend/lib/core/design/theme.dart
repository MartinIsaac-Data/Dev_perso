/// The Flutter theme, assembled from the tokens.
///
/// Replaces the phase-1 `app/theme.dart`, which used a seed colour and Material
/// defaults. A generated scheme is a fine starting point and a poor destination:
/// it produces tinted surfaces and large radii that pull the product towards
/// "consumer app" when it wants to read as a tool.
library;

import 'package:flutter/material.dart';

import '../api/models.dart';
import 'palette.dart';
import 'tokens.dart';

ThemeData buildAppTheme(Brightness brightness) {
  final scheme = brightness == Brightness.dark ? darkScheme : lightScheme;
  final text = _textTheme(scheme);

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    textTheme: text,
    // Material's ink splash is a phone idiom. On a dense keyboard-driven list it
    // reads as noise, so interaction is signalled by a background change alone.
    splashFactory: NoSplash.splashFactory,
    highlightColor: Colors.transparent,
    visualDensity: VisualDensity.compact,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      foregroundColor: scheme.onSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: text.titleMedium,
    ),
    dividerTheme: DividerThemeData(
      color: scheme.outlineVariant,
      thickness: 1,
      space: 1,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainer,
      hintStyle: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
      contentPadding: const EdgeInsets.symmetric(
        horizontal: Space.md,
        vertical: Space.md,
      ),
      border: OutlineInputBorder(
        borderRadius: Radii.mdAll,
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: Radii.mdAll,
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: Radii.mdAll,
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: Radii.mdAll,
        borderSide: BorderSide(color: scheme.error),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(0, 40),
        padding: const EdgeInsets.symmetric(horizontal: Space.lg),
        shape: const RoundedRectangleBorder(borderRadius: Radii.mdAll),
        textStyle: text.labelLarge,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, 40),
        padding: const EdgeInsets.symmetric(horizontal: Space.lg),
        shape: const RoundedRectangleBorder(borderRadius: Radii.mdAll),
        side: BorderSide(color: scheme.outlineVariant),
        textStyle: text.labelLarge,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(0, 36),
        padding: const EdgeInsets.symmetric(horizontal: Space.md),
        shape: const RoundedRectangleBorder(borderRadius: Radii.smAll),
        textStyle: text.labelLarge,
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(
        minimumSize: const Size(32, 32),
        shape: const RoundedRectangleBorder(borderRadius: Radii.smAll),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: scheme.surfaceContainer,
      selectedColor: scheme.primaryContainer,
      side: BorderSide(color: scheme.outlineVariant),
      labelStyle: text.labelMedium,
      padding: const EdgeInsets.symmetric(horizontal: Space.sm, vertical: 2),
      shape: const RoundedRectangleBorder(borderRadius: Radii.smAll),
      showCheckmark: false,
    ),
    listTileTheme: ListTileThemeData(
      dense: true,
      minVerticalPadding: Space.sm,
      shape: const RoundedRectangleBorder(borderRadius: Radii.smAll),
      iconColor: scheme.onSurfaceVariant,
    ),
    tooltipTheme: TooltipThemeData(
      waitDuration: const Duration(milliseconds: 500),
      decoration: BoxDecoration(
        color: scheme.inverseSurface,
        borderRadius: Radii.smAll,
      ),
      textStyle: text.labelSmall?.copyWith(color: scheme.onInverseSurface),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: scheme.inverseSurface,
      contentTextStyle:
          text.bodyMedium?.copyWith(color: scheme.onInverseSurface),
      shape: const RoundedRectangleBorder(borderRadius: Radii.mdAll),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: scheme.surfaceContainerLow,
      surfaceTintColor: Colors.transparent,
      shape: const RoundedRectangleBorder(borderRadius: Radii.xlAll),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      linearMinHeight: 3,
      color: scheme.primary,
      linearTrackColor: scheme.surfaceContainerHigh,
    ),
    scrollbarTheme: ScrollbarThemeData(
      thickness: WidgetStateProperty.all(6),
      radius: const Radius.circular(Radii.pill),
      thumbColor: WidgetStateProperty.all(scheme.outline),
    ),
  );
}

/// Type scale.
///
/// Tight line heights in the dense parts of the interface, generous ones in the
/// reading parts. A transcript set at the same leading as a list row is
/// exhausting to read, and a list row set at reading leading wastes half the
/// screen.
TextTheme _textTheme(ColorScheme scheme) {
  final onSurface = scheme.onSurface;
  final muted = scheme.onSurfaceVariant;

  return TextTheme(
    displaySmall: TextStyle(
      fontSize: 32,
      height: 1.15,
      letterSpacing: -0.6,
      fontWeight: FontWeight.w600,
      color: onSurface,
    ),
    headlineSmall: TextStyle(
      fontSize: 22,
      height: 1.25,
      letterSpacing: -0.3,
      fontWeight: FontWeight.w600,
      color: onSurface,
    ),
    titleLarge: TextStyle(
      fontSize: 18,
      height: 1.3,
      letterSpacing: -0.2,
      fontWeight: FontWeight.w600,
      color: onSurface,
    ),
    titleMedium: TextStyle(
      fontSize: 15,
      height: 1.35,
      letterSpacing: -0.1,
      fontWeight: FontWeight.w600,
      color: onSurface,
    ),
    titleSmall: TextStyle(
      fontSize: 13,
      height: 1.35,
      fontWeight: FontWeight.w600,
      color: onSurface,
    ),
    // Reading contexts: 1.6 leading, Notion-style.
    bodyLarge: TextStyle(fontSize: 15, height: 1.6, color: onSurface),
    bodyMedium: TextStyle(fontSize: 14, height: 1.5, color: onSurface),
    bodySmall: TextStyle(fontSize: 13, height: 1.45, color: muted),
    labelLarge: TextStyle(
      fontSize: 13,
      height: 1.2,
      fontWeight: FontWeight.w500,
      color: onSurface,
    ),
    labelMedium: TextStyle(
      fontSize: 12,
      height: 1.2,
      fontWeight: FontWeight.w500,
      color: muted,
    ),
    labelSmall: TextStyle(
      fontSize: 11,
      height: 1.2,
      letterSpacing: 0.1,
      fontWeight: FontWeight.w500,
      color: muted,
    ),
  );
}

// --------------------------------------------------------------------------- //
// Entry vocabulary — icon, colour and label per type
// --------------------------------------------------------------------------- //

/// Type is carried by an icon *and* a colour, never colour alone.
IconData entryIcon(EntryType type) => switch (type) {
      EntryType.task => Icons.check_circle_outline,
      EntryType.idea => Icons.lightbulb_outline,
      EntryType.decision => Icons.gavel_outlined,
      EntryType.question => Icons.help_outline,
      EntryType.meeting => Icons.groups_outlined,
      EntryType.reminder => Icons.notifications_none,
      EntryType.note || EntryType.unknown => Icons.notes_outlined,
    };

Color entryColor(ColorScheme scheme, EntryType type) => switch (type) {
      EntryType.task => scheme.primary,
      EntryType.idea => Palette.idea,
      EntryType.decision => Palette.decision,
      EntryType.question => Palette.question,
      EntryType.meeting => Palette.meeting,
      EntryType.reminder => Palette.reminder,
      EntryType.note || EntryType.unknown => scheme.onSurfaceVariant,
    };

String entryTypeLabel(EntryType type) => switch (type) {
      EntryType.task => 'Tâche',
      EntryType.idea => 'Idée',
      EntryType.decision => 'Décision',
      EntryType.question => 'Question',
      EntryType.meeting => 'Réunion',
      EntryType.reminder => 'Rappel',
      EntryType.note => 'Note',
      EntryType.unknown => 'Élément',
    };

/// Priority reads as a *rank*, so it gets a bar rather than a coloured dot —
/// four bars of increasing height say "more" without relying on hue.
IconData priorityIcon(String priority) => switch (priority) {
      'urgent' => Icons.keyboard_double_arrow_up,
      'high' => Icons.keyboard_arrow_up,
      'low' => Icons.keyboard_arrow_down,
      _ => Icons.remove,
    };

Color priorityColor(ColorScheme scheme, String priority) => switch (priority) {
      'urgent' => scheme.error,
      'high' => Palette.warning,
      'low' => scheme.onSurfaceVariant,
      _ => scheme.onSurfaceVariant,
    };

String priorityLabel(String priority) => switch (priority) {
      'urgent' => 'Urgent',
      'high' => 'Important',
      'low' => 'Basse',
      _ => 'Normale',
    };

/// A card surface, applied by hand.
///
/// `ThemeData.cardTheme` changed type between Flutter versions; a helper is one
/// line and survives the churn.
BoxDecoration cardDecoration(ColorScheme scheme, {bool selected = false}) =>
    BoxDecoration(
      color: selected ? scheme.primaryContainer : scheme.surfaceContainerLow,
      borderRadius: Radii.lgAll,
      border: Border.all(
        color: selected ? scheme.primary : scheme.outlineVariant,
      ),
    );
