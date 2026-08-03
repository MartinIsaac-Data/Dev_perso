/// Visual language.
///
/// One accent colour and a lot of white space. The product's promise is that
/// capturing a thought takes no attention; a busy interface would contradict it
/// on the first screen.
library;

import 'package:flutter/material.dart';

import '../core/api/models.dart';

const kSeed = Color(0xFF3D5AFE);

ThemeData buildTheme(Brightness brightness) {
  final scheme = ColorScheme.fromSeed(seedColor: kSeed, brightness: brightness);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: scheme.onSurface,
        fontSize: 20,
        fontWeight: FontWeight.w600,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHighest,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
      side: BorderSide(color: scheme.outlineVariant),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
  );
}

/// Card surface, applied by hand rather than through `ThemeData.cardTheme`.
/// The theme-data classes for cards were renamed between Flutter versions;
/// a helper is one line and survives the churn.
BoxDecoration cardDecoration(ColorScheme scheme) => BoxDecoration(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: scheme.outlineVariant),
    );

/// Type is carried by an icon and a colour, never by colour alone: roughly one
/// man in twelve would not see the difference otherwise.
IconData entryIcon(EntryType type) => switch (type) {
      EntryType.task => Icons.check_circle_outline,
      EntryType.idea => Icons.lightbulb_outline,
      EntryType.decision => Icons.gavel_outlined,
      EntryType.question => Icons.help_outline,
      EntryType.meeting => Icons.groups_outlined,
      EntryType.reminder => Icons.alarm_outlined,
      EntryType.note || EntryType.unknown => Icons.notes_outlined,
    };

Color entryColor(ColorScheme scheme, EntryType type) => switch (type) {
      EntryType.task => scheme.primary,
      EntryType.idea => const Color(0xFFF9A825),
      EntryType.decision => const Color(0xFF00897B),
      EntryType.question => const Color(0xFF8E24AA),
      EntryType.meeting => const Color(0xFF5E35B1),
      EntryType.reminder => const Color(0xFFE64A19),
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
