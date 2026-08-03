/// Superseded by `core/design/theme.dart` in phase 2.
///
/// Kept as a re-export rather than deleted: the phase-1 screens import
/// `entryIcon`, `entryColor` and `entryTypeLabel` from here, and rewriting five
/// import lines to prove a point is churn, not progress. The definitions now
/// live with the rest of the design system.
library;

export '../core/design/theme.dart'
    show buildAppTheme, cardDecoration, entryColor, entryIcon, entryTypeLabel;
