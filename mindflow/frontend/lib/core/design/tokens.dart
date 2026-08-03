/// Design tokens.
///
/// The visual language borrows deliberately from four products and from each one
/// only the thing it is actually good at:
///
/// * **Linear** — density and restraint. Small radii, hairline borders, a single
///   accent used sparingly, and text that carries the hierarchy instead of boxes
///   and shadows. Nothing decorative earns its pixels.
/// * **Notion** — calm typography and generous line height in reading contexts.
///   A transcript is prose and should read like prose.
/// * **Raycast** — the command palette as the primary navigation. Everything
///   reachable from one keystroke, ranked, with the keyboard hint visible.
/// * **ChatGPT** — a content column that never exceeds a comfortable measure,
///   whatever the window width.
///
/// Every value here is a *decision*, not a preference: they exist in one file so
/// that changing the density of the product is one edit rather than fifty.
library;

import 'package:flutter/widgets.dart';

/// Spacing scale, in logical pixels. A 4-unit base keeps everything on a grid;
/// arbitrary paddings are what make an interface feel slightly wrong without
/// anyone being able to say why.
abstract final class Space {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
  static const double xxxl = 48;
}

/// Corner radii. Small, in the Linear manner — large radii read as "consumer
/// app", and this is a tool.
abstract final class Radii {
  static const double xs = 4;
  static const double sm = 6;
  static const double md = 8;
  static const double lg = 12;
  static const double xl = 16;
  static const double pill = 999;

  static const BorderRadius smAll = BorderRadius.all(Radius.circular(sm));
  static const BorderRadius mdAll = BorderRadius.all(Radius.circular(md));
  static const BorderRadius lgAll = BorderRadius.all(Radius.circular(lg));
  static const BorderRadius xlAll = BorderRadius.all(Radius.circular(xl));
  static const BorderRadius pillAll = BorderRadius.all(Radius.circular(pill));
}

/// Motion. Short and few: an interface a person uses fifty times a day must not
/// make them wait for an animation, and anything past ~200 ms is felt as lag
/// rather than as polish.
abstract final class Motion {
  static const Duration instant = Duration(milliseconds: 90);
  static const Duration fast = Duration(milliseconds: 140);
  static const Duration normal = Duration(milliseconds: 200);

  static const Curve easeOut = Curves.easeOutCubic;
  static const Curve standard = Curves.easeInOutCubic;
}

/// Layout breakpoints and measures.
abstract final class Layout {
  /// Below this, the sidebar collapses into a bottom navigation bar.
  static const double compactMax = 720;

  /// Above this, a detail pane can sit beside the list.
  static const double expandedMin = 1100;

  /// The reading measure, borrowed from ChatGPT: content stops widening well
  /// before the window does. Long lines are measurably harder to read, and a
  /// 2000-pixel-wide paragraph is nobody's idea of comfortable.
  static const double contentMax = 760;

  /// Wide enough for a date and a couple of chips without wrapping.
  static const double sidebarWidth = 248;

  /// Fixed row height for the entry list. Not cosmetic: giving `ListView`
  /// a `prototypeItem` of a known height lets it compute scroll extents without
  /// laying out off-screen children, which is what keeps a list of ten thousand
  /// rows scrolling at frame rate.
  static const double entryRowHeight = 64;
  static const double compactRowHeight = 44;
}

/// Named durations for data freshness, so caching decisions are visible.
abstract final class Freshness {
  /// The command palette debounce. Long enough that typing "réunion" is one
  /// request instead of seven; short enough not to feel stuck.
  static const Duration paletteDebounce = Duration(milliseconds: 180);

  /// Full-text search runs a heavier query, so it waits a little longer.
  static const Duration searchDebounce = Duration(milliseconds: 320);
}
