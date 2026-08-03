/// The analytical dashboard.
///
/// The charts are hand-painted rather than drawn by a charting package. Three
/// reasons, in order of weight: the product needs exactly two chart types, a
/// package would add a dependency larger than the feature, and a `CustomPainter`
/// here paints a few dozen rectangles in one pass where a generic library builds
/// a widget per data point.
///
/// The section titled *Ce qui ne va pas* is deliberate and non-negotiable. A
/// dashboard that reports only what went well teaches nothing; the correction
/// rate and the captures that produced nothing are the numbers that say whether
/// the product is actually working.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/errors.dart';
import '../../core/api/planning_models.dart';
import '../../core/design/components.dart';
import '../../core/design/theme.dart';
import '../../core/design/tokens.dart';
import 'planning_providers.dart';

class AnalyticsScreen extends ConsumerWidget {
  const AnalyticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stats = ref.watch(statisticsProvider);
    final window = ref.watch(statsWindowProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Statistiques'),
        actions: [
          SegmentedButton<int>(
            segments: const [
              ButtonSegment(value: 7, label: Text('7 j')),
              ButtonSegment(value: 30, label: Text('30 j')),
              ButtonSegment(value: 90, label: Text('90 j')),
            ],
            selected: {window},
            showSelectedIcon: false,
            style: const ButtonStyle(visualDensity: VisualDensity.compact),
            onSelectionChanged: (selection) =>
                ref.read(statsWindowProvider.notifier).state = selection.first,
          ),
          const SizedBox(width: Space.sm),
        ],
      ),
      body: stats.when(
        loading: () => const MfSkeletonList(rows: 8),
        error: (error, _) => MfEmpty(
          icon: Icons.insights_outlined,
          title: 'Statistiques indisponibles',
          message: error is ApiException ? error.userMessage : null,
        ),
        data: (data) => _Body(stats: data),
      ),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.stats});

  final Statistics stats;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: Space.lg),
      children: [
        MfContentColumn(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _HeadlineRow(stats: stats),
              const MfSectionHeader(title: 'Activité'),
              _ActivityChart(points: stats.daily),
              const SizedBox(height: Space.md),
              const _ChartLegend(),
              if (stats.streak.current > 0) ...[
                const SizedBox(height: Space.lg),
                MfNotice(
                  icon: Icons.local_fire_department_outlined,
                  tone: MfNoticeTone.info,
                  message: '${stats.streak.current} jours de capture d’affilée '
                      '(record : ${stats.streak.longest}).',
                ),
              ],
              if (stats.byType.isNotEmpty) ...[
                const MfSectionHeader(title: 'Par type'),
                _BreakdownList(items: stats.byType),
              ],
              if (stats.byPriority.isNotEmpty) ...[
                const MfSectionHeader(title: 'Par priorité'),
                _BreakdownList(items: stats.byPriority),
              ],
              if (stats.byProject.isNotEmpty) ...[
                const MfSectionHeader(title: 'Par projet'),
                _BreakdownList(items: stats.byProject),
              ],
              if (stats.topTags.isNotEmpty) ...[
                const MfSectionHeader(title: 'Tags les plus utilisés'),
                _TagCloud(tags: stats.topTags),
              ],
              const MfSectionHeader(title: 'Ce qui ne va pas'),
              _HonestSection(stats: stats),
              const SizedBox(height: Space.xxxl),
            ],
          ),
        ),
      ],
    );
  }
}

class _HeadlineRow extends StatelessWidget {
  const _HeadlineRow({required this.stats});

  final Statistics stats;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: Space.md,
      runSpacing: Space.md,
      children: [
        _Metric(
          value: '${stats.captures}',
          label: 'captures',
          icon: Icons.graphic_eq,
        ),
        _Metric(
          value: '${stats.tasksCompleted}',
          label: 'tâches terminées',
          icon: Icons.check_circle_outline,
        ),
        _Metric(
          value: '${stats.tasksOpen}',
          label: 'en cours',
          icon: Icons.radio_button_unchecked,
        ),
        _Metric(
          value: '${stats.tasksOverdue}',
          label: 'en retard',
          icon: Icons.error_outline,
          tone:
              stats.tasksOverdue > 0 ? _MetricTone.danger : _MetricTone.neutral,
        ),
        _Metric(
          value: '${(stats.completionRate * 100).round()} %',
          label: 'taux de complétion',
          icon: Icons.percent,
        ),
        if (stats.medianCompletionHours != null)
          _Metric(
            value: _duration(stats.medianCompletionHours!),
            label: 'délai médian',
            icon: Icons.timelapse_outlined,
          ),
      ],
    );
  }

  static String _duration(double hours) {
    if (hours < 1) return '${(hours * 60).round()} min';
    if (hours < 48) return '${hours.round()} h';
    return '${(hours / 24).round()} j';
  }
}

enum _MetricTone { neutral, danger }

class _Metric extends StatelessWidget {
  const _Metric({
    required this.value,
    required this.label,
    required this.icon,
    this.tone = _MetricTone.neutral,
  });

  final String value;
  final String label;
  final IconData icon;
  final _MetricTone tone;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final accent = tone == _MetricTone.danger ? scheme.error : scheme.onSurface;

    return Container(
      width: 156,
      padding: const EdgeInsets.all(Space.md),
      decoration: cardDecoration(scheme),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 14, color: scheme.onSurfaceVariant),
          const SizedBox(height: Space.sm),
          Text(
            value,
            style: theme.textTheme.headlineSmall?.copyWith(color: accent),
          ),
          Text(label, style: theme.textTheme.labelSmall),
        ],
      ),
    );
  }
}

/// A grouped bar chart: created, completed and captured per day.
class _ActivityChart extends StatelessWidget {
  const _ActivityChart({required this.points});

  final List<DailyPoint> points;

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) {
      return const MfEmpty(
          icon: Icons.bar_chart, title: 'Pas encore de données');
    }
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      height: 140,
      // RepaintBoundary: the chart is expensive to paint and never changes while
      // the rest of the page scrolls, so it should not be repainted with it.
      child: RepaintBoundary(
        child: CustomPaint(
          painter: _ActivityPainter(
            points: points,
            created: scheme.primary,
            completed: scheme.tertiary,
            captured: scheme.outline,
            grid: scheme.outlineVariant,
          ),
          child: const SizedBox.expand(),
        ),
      ),
    );
  }
}

class _ActivityPainter extends CustomPainter {
  _ActivityPainter({
    required this.points,
    required this.created,
    required this.completed,
    required this.captured,
    required this.grid,
  });

  final List<DailyPoint> points;
  final Color created;
  final Color completed;
  final Color captured;
  final Color grid;

  @override
  void paint(Canvas canvas, Size size) {
    final maximum = points.fold<int>(
        1, (best, point) => point.max > best ? point.max : best);
    final slotWidth = size.width / points.length;
    // Three bars per day plus a gap. Below ~1 px a bar disappears entirely, so
    // the width is floored — an invisible bar reads as missing data.
    final barWidth = ((slotWidth - 2) / 3).clamp(1.0, 6.0);

    final baseline = Paint()
      ..color = grid
      ..strokeWidth = 1;
    canvas.drawLine(
      Offset(0, size.height - 0.5),
      Offset(size.width, size.height - 0.5),
      baseline,
    );

    for (var index = 0; index < points.length; index++) {
      final point = points[index];
      final left = index * slotWidth + 1;
      _bar(canvas, size, left, point.created, maximum, barWidth, created);
      _bar(canvas, size, left + barWidth, point.completed, maximum, barWidth,
          completed);
      _bar(canvas, size, left + barWidth * 2, point.captured, maximum, barWidth,
          captured);
    }
  }

  void _bar(
    Canvas canvas,
    Size size,
    double left,
    int value,
    int maximum,
    double width,
    Color color,
  ) {
    if (value == 0) return;
    final height = (value / maximum) * (size.height - 4);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(left, size.height - height, width - 0.5, height),
        const Radius.circular(1),
      ),
      Paint()..color = color,
    );
  }

  @override
  bool shouldRepaint(_ActivityPainter oldDelegate) =>
      oldDelegate.points != points || oldDelegate.created != created;
}

class _ChartLegend extends StatelessWidget {
  const _ChartLegend();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Wrap(
      spacing: Space.lg,
      children: [
        _LegendDot(color: scheme.primary, label: 'Créées'),
        _LegendDot(color: scheme.tertiary, label: 'Terminées'),
        _LegendDot(color: scheme.outline, label: 'Captures'),
      ],
    );
  }
}

class _LegendDot extends StatelessWidget {
  const _LegendDot({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
              color: color, borderRadius: BorderRadius.circular(2)),
        ),
        const SizedBox(width: Space.xs),
        MfMeta(label: label),
      ],
    );
  }
}

/// Horizontal bars with a label and a count. Sorted by the server; rendering
/// preserves that order rather than re-sorting, so the two never disagree.
class _BreakdownList extends StatelessWidget {
  const _BreakdownList({required this.items});

  final List<Breakdown> items;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final maximum = items.fold<int>(
        1, (best, item) => item.total > best ? item.total : best);

    return Column(
      children: [
        for (final item in items)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.sm),
            child: Row(
              children: [
                SizedBox(
                  width: 120,
                  child: Text(
                    item.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall,
                  ),
                ),
                Expanded(
                  child: MfProgressBar(
                    value: item.total / maximum,
                    height: 6,
                    color: _parseColor(item.color) ?? scheme.primary,
                  ),
                ),
                const SizedBox(width: Space.md),
                SizedBox(
                  width: 56,
                  child: Text(
                    item.done > 0
                        ? '${item.done}/${item.total}'
                        : '${item.total}',
                    textAlign: TextAlign.right,
                    style: theme.textTheme.labelSmall,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _TagCloud extends StatelessWidget {
  const _TagCloud({required this.tags});

  final List<Breakdown> tags;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: Space.sm,
      runSpacing: Space.sm,
      children: [
        for (final tag in tags)
          MfChip(
              label: '${tag.label} · ${tag.total}',
              color: _parseColor(tag.color)),
      ],
    );
  }
}

/// The uncomfortable numbers, given the same prominence as the flattering ones.
class _HonestSection extends StatelessWidget {
  const _HonestSection({required this.stats});

  final Statistics stats;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rows = <(String, String, String?)>[
      (
        'Extractions corrigées',
        '${(stats.correctionRate * 100).round()} % (${stats.corrections})',
        stats.correctionRate > 0.3
            ? "L'analyse s'écarte de votre façon de parler."
            : null,
      ),
      (
        'Captures sans résultat',
        '${stats.capturesWithoutEntries}',
        stats.capturesWithoutEntries > 0
            ? 'Enregistrements dont rien n’a été tiré.'
            : null,
      ),
      ('À vérifier', '${stats.needsReview}', null),
      (
        'Coût IA sur la période',
        '${stats.aiCostEur.toStringAsFixed(2)} €',
        null
      ),
      if (stats.busiestHour != null)
        ('Heure de capture la plus fréquente', '${stats.busiestHour} h', null),
    ];

    return Column(
      children: [
        for (final (label, value, note) in rows)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(label, style: theme.textTheme.bodySmall),
                      if (note != null)
                        Text(note, style: theme.textTheme.labelSmall),
                    ],
                  ),
                ),
                Text(value, style: theme.textTheme.titleSmall),
              ],
            ),
          ),
      ],
    );
  }
}

Color? _parseColor(String? hex) {
  if (hex == null || hex.length != 7 || !hex.startsWith('#')) return null;
  final value = int.tryParse(hex.substring(1), radix: 16);
  return value == null ? null : Color(0xFF000000 | value);
}
