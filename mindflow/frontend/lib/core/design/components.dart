/// The shared widget vocabulary.
///
/// These exist so that a status pill looks the same on the agenda, the search
/// results and the timeline. The moment three screens each roll their own, the
/// product stops looking like one thing.
///
/// Every widget here is `const`-constructible where the data allows it. That is
/// a performance decision as much as a style one: a `const` widget is skipped
/// entirely during rebuild, and in a list of sixty rows with five chips each,
/// that is three hundred subtrees the framework does not have to visit.
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

/// A small labelled pill. The workhorse of the whole interface.
class MfChip extends StatelessWidget {
  const MfChip({
    required this.label,
    this.icon,
    this.color,
    this.background,
    this.onTap,
    this.selected = false,
    super.key,
  });

  final String label;
  final IconData? icon;
  final Color? color;
  final Color? background;
  final VoidCallback? onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final foreground = color ??
        (selected ? scheme.onPrimaryContainer : scheme.onSurfaceVariant);

    final content = Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.sm, vertical: 3),
      decoration: BoxDecoration(
        color: background ??
            (selected ? scheme.primaryContainer : Colors.transparent),
        borderRadius: Radii.smAll,
        border: Border.all(
          color: selected ? scheme.primary : scheme.outlineVariant,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 12, color: foreground),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: theme.textTheme.labelSmall?.copyWith(
              color: foreground,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );

    if (onTap == null) return content;
    return InkWell(
      onTap: onTap,
      borderRadius: Radii.smAll,
      child: content,
    );
  }
}

/// Metadata shown inline on a row: an icon and a word, nothing more.
class MfMeta extends StatelessWidget {
  const MfMeta({required this.label, this.icon, this.color, super.key});

  final String label;
  final IconData? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tint = color ?? theme.colorScheme.onSurfaceVariant;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 12, color: tint),
          const SizedBox(width: 3),
        ],
        Text(label, style: theme.textTheme.labelSmall?.copyWith(color: tint)),
      ],
    );
  }
}

/// The keyboard hint, Raycast-style: the shortcut is *visible*, not hidden in a
/// help page nobody opens.
class MfKeyHint extends StatelessWidget {
  const MfKeyHint(this.keys, {super.key});

  final List<String> keys;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final key in keys)
          Container(
            margin: const EdgeInsets.only(left: 3),
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHigh,
              borderRadius: Radii.smAll,
              border: Border.all(color: scheme.outlineVariant),
            ),
            child: Text(
              key,
              style: TextStyle(
                fontSize: 10,
                height: 1.4,
                fontWeight: FontWeight.w600,
                color: scheme.onSurfaceVariant,
              ),
            ),
          ),
      ],
    );
  }
}

/// A section heading: a quiet uppercase label with an optional count.
class MfSectionHeader extends StatelessWidget {
  const MfSectionHeader({
    required this.title,
    this.count,
    this.action,
    this.padding = const EdgeInsets.fromLTRB(0, Space.xl, 0, Space.sm),
    super.key,
  });

  final String title;
  final int? count;
  final Widget? action;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: padding,
      child: Row(
        children: [
          Text(
            title.toUpperCase(),
            style: theme.textTheme.labelSmall?.copyWith(
              letterSpacing: 0.7,
              fontWeight: FontWeight.w600,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (count != null) ...[
            const SizedBox(width: Space.sm),
            Text(
              '$count',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
          const Spacer(),
          if (action != null) action!,
        ],
      ),
    );
  }
}

/// The empty state. Says what to do next, not merely that there is nothing.
class MfEmpty extends StatelessWidget {
  const MfEmpty({
    required this.icon,
    required this.title,
    this.message,
    this.action,
    super.key,
  });

  final IconData icon;
  final String title;
  final String? message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(Space.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 32, color: theme.colorScheme.outline),
            const SizedBox(height: Space.lg),
            Text(title, style: theme.textTheme.titleSmall),
            if (message != null) ...[
              const SizedBox(height: Space.xs),
              Text(
                message!,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall,
              ),
            ],
            if (action != null) ...[
              const SizedBox(height: Space.lg),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

/// A loading placeholder shaped like the content it replaces.
///
/// A skeleton beats a spinner because it does not move the layout when the data
/// arrives — the page does not "jump", which is the single most common cause of
/// a mis-tap.
class MfSkeleton extends StatefulWidget {
  const MfSkeleton({
    this.height = 14,
    this.width,
    this.borderRadius = Radii.smAll,
    super.key,
  });

  final double height;
  final double? width;
  final BorderRadius borderRadius;

  @override
  State<MfSkeleton> createState() => _MfSkeletonState();
}

class _MfSkeletonState extends State<MfSkeleton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // The animation drives only the decoration, and the child subtree is built
    // once outside the builder — otherwise every frame rebuilds a widget tree
    // to change one colour.
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) => Container(
        height: widget.height,
        width: widget.width,
        decoration: BoxDecoration(
          color: Color.lerp(
            scheme.surfaceContainer,
            scheme.surfaceContainerHigh,
            _controller.value,
          ),
          borderRadius: widget.borderRadius,
        ),
      ),
    );
  }
}

/// A list of skeleton rows, for a list that is still loading.
class MfSkeletonList extends StatelessWidget {
  const MfSkeletonList({this.rows = 6, super.key});

  final int rows;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: const EdgeInsets.all(Space.lg),
      itemCount: rows,
      itemExtent: Layout.entryRowHeight,
      itemBuilder: (context, index) => const Padding(
        padding: EdgeInsets.symmetric(vertical: Space.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            MfSkeleton(width: 220),
            SizedBox(height: Space.sm),
            MfSkeleton(height: 10, width: 120),
          ],
        ),
      ),
    );
  }
}

/// Constrains content to a comfortable reading measure, ChatGPT-style: the
/// column stops widening well before the window does.
class MfContentColumn extends StatelessWidget {
  const MfContentColumn({
    required this.child,
    this.maxWidth = Layout.contentMax,
    this.padding = const EdgeInsets.symmetric(horizontal: Space.lg),
    super.key,
  });

  final Widget child;
  final double maxWidth;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}

/// A notice bar. Used for degraded states, which this product has several of and
/// always states plainly rather than hiding.
class MfNotice extends StatelessWidget {
  const MfNotice({
    required this.icon,
    required this.message,
    this.action,
    this.tone = MfNoticeTone.neutral,
    super.key,
  });

  final IconData icon;
  final String message;
  final Widget? action;
  final MfNoticeTone tone;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (background, foreground) = switch (tone) {
      MfNoticeTone.neutral => (
          scheme.surfaceContainer,
          scheme.onSurfaceVariant
        ),
      MfNoticeTone.info => (scheme.primaryContainer, scheme.onPrimaryContainer),
      MfNoticeTone.warning => (
          scheme.tertiaryContainer,
          scheme.onTertiaryContainer
        ),
      MfNoticeTone.danger => (scheme.errorContainer, scheme.onErrorContainer),
    };

    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.sm),
      decoration: BoxDecoration(
        color: background,
        borderRadius: Radii.mdAll,
      ),
      child: Row(
        children: [
          Icon(icon, size: 16, color: foreground),
          const SizedBox(width: Space.sm),
          Expanded(
            child: Text(
              message,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: foreground),
            ),
          ),
          if (action != null) action!,
        ],
      ),
    );
  }
}

enum MfNoticeTone { neutral, info, warning, danger }

/// A thin progress bar for subtask completion. Deliberately not a percentage
/// label: "3/5" is instantly legible and "60 %" is not.
class MfProgressBar extends StatelessWidget {
  const MfProgressBar({
    required this.value,
    this.height = 3,
    this.color,
    super.key,
  });

  final double value;
  final double height;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ClipRRect(
      borderRadius: Radii.pillAll,
      child: SizedBox(
        height: height,
        child: LinearProgressIndicator(
          value: value.clamp(0.0, 1.0),
          backgroundColor: scheme.surfaceContainerHigh,
          valueColor: AlwaysStoppedAnimation(color ?? scheme.primary),
        ),
      ),
    );
  }
}
