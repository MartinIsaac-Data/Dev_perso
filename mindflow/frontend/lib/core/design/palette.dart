/// Colour, defined once.
///
/// Two decisions shape everything below.
///
/// **Neutral-first.** The surface, the borders and the text are greys with a
/// faint blue cast; the accent appears on exactly one thing per screen. An
/// interface that colours everything has no way left to say "this matters" —
/// which is the whole job of an accent.
///
/// **Dark is designed, not derived.** The dark palette is not the light one
/// inverted: it uses lifted surfaces rather than pure black (which smears on
/// OLED and makes elevation impossible to read) and slightly desaturated accents
/// (which glow unpleasantly at full saturation on a dark field).
///
/// Semantic colours are always paired with an icon or a label elsewhere in the
/// interface. Roughly one man in twelve cannot distinguish the red from the
/// green here, so colour never carries meaning on its own.
library;

import 'package:flutter/material.dart';

abstract final class Palette {
  // The accent. One hue, two tones — the dark variant is lighter and less
  // saturated so it does not vibrate against a dark surface.
  static const Color accent = Color(0xFF5B5BD6);
  static const Color accentDark = Color(0xFF8E8BF5);

  // Semantic. Used with icons, never alone.
  static const Color danger = Color(0xFFE5484D);
  static const Color dangerDark = Color(0xFFFF6369);
  static const Color warning = Color(0xFFF5A524);
  static const Color success = Color(0xFF30A46C);
  static const Color info = Color(0xFF0091FF);

  // Entry-type hues. Distinct in *lightness* as well as hue, so they remain
  // distinguishable in greyscale and to a colour-blind reader.
  static const Color task = Color(0xFF5B5BD6);
  static const Color idea = Color(0xFFF5A524);
  static const Color note = Color(0xFF6E7681);
  static const Color decision = Color(0xFF12A594);
  static const Color question = Color(0xFF8E4EC6);
  static const Color meeting = Color(0xFF3E63DD);
  static const Color reminder = Color(0xFFE5484D);
}

/// Light scheme — near-white surfaces, hairline borders, dark text.
const ColorScheme lightScheme = ColorScheme(
  brightness: Brightness.light,
  primary: Palette.accent,
  onPrimary: Color(0xFFFFFFFF),
  primaryContainer: Color(0xFFEBEBFE),
  onPrimaryContainer: Color(0xFF2B2B78),
  secondary: Color(0xFF5E6470),
  onSecondary: Color(0xFFFFFFFF),
  secondaryContainer: Color(0xFFF1F2F4),
  onSecondaryContainer: Color(0xFF2C3038),
  tertiary: Color(0xFF8E4EC6),
  onTertiary: Color(0xFFFFFFFF),
  tertiaryContainer: Color(0xFFF3E7FC),
  onTertiaryContainer: Color(0xFF4A1D6B),
  error: Palette.danger,
  onError: Color(0xFFFFFFFF),
  errorContainer: Color(0xFFFFEBEC),
  onErrorContainer: Color(0xFF7A1418),
  surface: Color(0xFFFFFFFF),
  onSurface: Color(0xFF16181D),
  onSurfaceVariant: Color(0xFF60646C),
  surfaceContainerLowest: Color(0xFFFFFFFF),
  surfaceContainerLow: Color(0xFFFBFBFC),
  surfaceContainer: Color(0xFFF6F7F8),
  surfaceContainerHigh: Color(0xFFF1F2F4),
  surfaceContainerHighest: Color(0xFFEBECEF),
  outline: Color(0xFFC5C8CD),
  outlineVariant: Color(0xFFE4E5E9),
  inverseSurface: Color(0xFF1C1F24),
  onInverseSurface: Color(0xFFF5F6F7),
  inversePrimary: Palette.accentDark,
  shadow: Color(0x14000000),
  scrim: Color(0x66000000),
);

/// Dark scheme — lifted greys rather than black, softened accents.
const ColorScheme darkScheme = ColorScheme(
  brightness: Brightness.dark,
  primary: Palette.accentDark,
  onPrimary: Color(0xFF10102E),
  primaryContainer: Color(0xFF2B2B5C),
  onPrimaryContainer: Color(0xFFE0E0FE),
  secondary: Color(0xFFA0A6B0),
  onSecondary: Color(0xFF16181D),
  secondaryContainer: Color(0xFF272A30),
  onSecondaryContainer: Color(0xFFE3E5E8),
  tertiary: Color(0xFFBF7AF0),
  onTertiary: Color(0xFF25103A),
  tertiaryContainer: Color(0xFF3D2255),
  onTertiaryContainer: Color(0xFFF0DDFC),
  error: Palette.dangerDark,
  onError: Color(0xFF3B0709),
  errorContainer: Color(0xFF4D1417),
  onErrorContainer: Color(0xFFFFD5D7),
  // Not #000: pure black removes every cue of elevation and smears on OLED
  // during scrolling.
  surface: Color(0xFF111317),
  onSurface: Color(0xFFEDEEF0),
  onSurfaceVariant: Color(0xFF9BA1A9),
  surfaceContainerLowest: Color(0xFF0C0E11),
  surfaceContainerLow: Color(0xFF15171B),
  surfaceContainer: Color(0xFF1A1D22),
  surfaceContainerHigh: Color(0xFF212429),
  surfaceContainerHighest: Color(0xFF282C32),
  outline: Color(0xFF3C4048),
  outlineVariant: Color(0xFF2A2D33),
  inverseSurface: Color(0xFFEDEEF0),
  onInverseSurface: Color(0xFF16181D),
  inversePrimary: Palette.accent,
  shadow: Color(0x33000000),
  scrim: Color(0x99000000),
);
