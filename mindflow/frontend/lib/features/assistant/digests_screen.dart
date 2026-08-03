/// Daily, weekly and monthly summaries.
///
/// Read like a feed, not like a report: newest first, one card per period, the
/// text unadorned. A digest is prose and gets the Notion half of the design
/// language — generous leading, a bounded measure, nothing competing with the
/// words.
///
/// The counts appear as small chips beside the text rather than inside it. They
/// were computed in SQL and handed to the model as facts precisely so they could
/// be trusted; showing them separately makes the distinction visible — these are
/// exact, the paragraph is a reading of them.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/assistant_models.dart';
import '../../core/api/client.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import 'assistant_providers.dart';

/// Statistic keys the API returns, in the order a reader wants them and with
/// the French wording the rest of the product uses.
const _statLabels = <String, String>{
  'entries_created': 'notes',
  'tasks_created': 'tâches créées',
  'tasks_completed': 'terminées',
  'tasks_overdue': 'en retard',
  'meetings': 'réunions',
  'decisions': 'décisions',
};

class DigestsScreen extends ConsumerStatefulWidget {
  const DigestsScreen({super.key});

  @override
  ConsumerState<DigestsScreen> createState() => _DigestsScreenState();
}

class _DigestsScreenState extends ConsumerState<DigestsScreen> {
  DigestPeriod? _period;
  bool _generating = false;

  Future<void> _generate() async {
    setState(() => _generating = true);
    try {
      await ref
          .read(apiProvider)
          .generateDigest(_period ?? DigestPeriod.daily, force: true);
      ref.invalidate(digestsProvider);
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final digests = ref.watch(digestsProvider(_period));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Résumés'),
        actions: [
          IconButton(
            onPressed: _generating ? null : _generate,
            icon: _generating
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
            tooltip: 'Générer maintenant',
          ),
        ],
      ),
      body: Column(
        children: [
          SizedBox(
            height: 52,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Space.lg),
              children: [
                _PeriodFilter(
                  label: 'Tous',
                  selected: _period == null,
                  onTap: () => setState(() => _period = null),
                ),
                for (final period in DigestPeriod.values)
                  _PeriodFilter(
                    label: period.label,
                    selected: _period == period,
                    onTap: () => setState(() => _period = period),
                  ),
              ],
            ),
          ),
          Expanded(
            child: digests.when(
              loading: () => const MfSkeletonList(),
              error: (error, _) => MfEmpty(
                icon: Icons.error_outline,
                title: 'Impossible de charger les résumés',
                message: '$error',
              ),
              data: (rows) => rows.isEmpty
                  ? const MfEmpty(
                      icon: Icons.article_outlined,
                      title: 'Aucun résumé pour l\'instant',
                      // Says when they arrive, so an empty list reads as "not
                      // yet" rather than "broken".
                      message: 'Le résumé du jour est produit chaque soir, '
                          'l\'hebdomadaire le lundi matin. Vous pouvez aussi en '
                          'générer un maintenant.',
                    )
                  : MfContentColumn(
                      child: ListView.builder(
                        padding: const EdgeInsets.symmetric(vertical: Space.lg),
                        itemCount: rows.length,
                        itemBuilder: (context, index) =>
                            _DigestCard(digest: rows[index]),
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PeriodFilter extends StatelessWidget {
  const _PeriodFilter({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: Space.sm),
      child: Center(
        child: FilterChip(
          label: Text(label),
          selected: selected,
          onSelected: (_) => onTap(),
        ),
      ),
    );
  }
}

class _DigestCard extends ConsumerWidget {
  const _DigestCard({required this.digest});

  final Digest digest;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.only(bottom: Space.xl),
      child: Container(
        padding: const EdgeInsets.all(Space.lg),
        decoration: BoxDecoration(
          color: scheme.surfaceContainerLow,
          borderRadius: Radii.lgAll,
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                MfChip(label: digest.period.label),
                const SizedBox(width: Space.sm),
                Expanded(child: MfMeta(label: _range(digest))),
                if (!digest.isRead)
                  TextButton(
                    onPressed: () async {
                      await ref.read(apiProvider).markDigestRead(digest.id);
                      ref.invalidate(digestsProvider);
                    },
                    child: const Text('Marquer comme lu'),
                  ),
              ],
            ),
            const SizedBox(height: Space.md),
            SelectableText(
              digest.content,
              style: theme.textTheme.bodyMedium?.copyWith(height: 1.6),
            ),
            if (digest.stats.isNotEmpty) ...[
              const SizedBox(height: Space.md),
              Wrap(
                spacing: Space.sm,
                runSpacing: Space.xs,
                children: [
                  for (final entry in _statLabels.entries)
                    if ((digest.stats[entry.key] ?? 0) > 0)
                      MfMeta(
                        label: '${digest.stats[entry.key]} ${entry.value}',
                      ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _range(Digest digest) {
    final start = _day(digest.periodStart);
    if (digest.period == DigestPeriod.daily) return start;
    return '$start → ${_day(digest.periodEnd)}';
  }

  static String _day(DateTime value) =>
      '${value.day.toString().padLeft(2, '0')}/'
      '${value.month.toString().padLeft(2, '0')}';
}
