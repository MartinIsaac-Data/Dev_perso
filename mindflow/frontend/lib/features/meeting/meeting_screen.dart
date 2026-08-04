/// The live meeting screen.
///
/// One layout rule drives everything here: **the panel must stay quiet.** A
/// live assistant that fills a column with plausible-looking items nobody
/// agreed to is worse than one that shows nothing, because the reader stops
/// trusting it and then stops reading it. So the empty state says the panel is
/// working and empty on purpose, rather than showing a spinner that implies
/// something is coming.
///
/// Two things are surfaced that a more confident interface would hide:
///
/// * **lost blocks**, because a transcript with holes produces a summary that is
///   confidently incomplete, and only the person in the room can judge whether
///   that matters;
/// * **a degraded report**, because a report that looks complete and is not is
///   the exact failure this feature has to avoid.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/meeting_models.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import '../enterprise/enterprise_ui.dart';
import 'meeting_controller.dart';

class MeetingScreen extends ConsumerStatefulWidget {
  const MeetingScreen({super.key});

  @override
  ConsumerState<MeetingScreen> createState() => _MeetingScreenState();
}

class _MeetingScreenState extends ConsumerState<MeetingScreen> {
  @override
  void initState() {
    super.initState();
    // A meeting survives the application being killed, so the first question on
    // this screen is whether one is still open.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(meetingControllerProvider.notifier).restore();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(meetingControllerProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Réunion'),
        actions: [
          if (state.isRecording)
            TextButton(
              onPressed: () => _abandon(context),
              child: const Text('Abandonner'),
            ),
        ],
      ),
      body: MfContentColumn(
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: Space.lg),
          children: [
            _Header(state: state),
            if (state.message != null) ...[
              const SizedBox(height: Space.md),
              MfNotice(
                icon: Icons.info_outline,
                tone: MfNoticeTone.warning,
                message: state.message!,
              ),
            ],
            if (state.blocksLost > 0) ...[
              const SizedBox(height: Space.md),
              MfNotice(
                icon: Icons.signal_wifi_bad,
                tone: MfNoticeTone.warning,
                message: '${state.blocksLost} passage(s) n\'ont pas pu être '
                    'transcrits. Le compte rendu sera incomplet sur ces '
                    'moments-là.',
              ),
            ],
            const SizedBox(height: Space.lg),
            _Controls(state: state),
            if (state.report != null) ...[
              const SizedBox(height: Space.xl),
              _Report(report: state.report!),
            ] else ...[
              const MfSectionHeader(title: 'Relevé en direct'),
              _Suggestions(state: state),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _abandon(BuildContext context) async {
    final confirmed = await confirmDestructive(
      context,
      title: 'Abandonner la réunion ?',
      message: 'La transcription et ce qui a été relevé seront supprimés. '
          'Aucun compte rendu ne sera produit.',
      confirm: 'Abandonner',
    );
    if (!confirmed) return;
    await ref.read(meetingControllerProvider.notifier).abandon();
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.state});

  final MeetingState state;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final meeting = state.meeting;

    return Row(
      children: [
        if (state.isRecording)
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
              color: theme.colorScheme.error,
              shape: BoxShape.circle,
            ),
          ),
        if (state.isRecording) const SizedBox(width: Space.sm),
        Expanded(
          child: Text(
            meeting?.title ?? 'Réunion sans titre',
            style: theme.textTheme.titleMedium,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (state.isRecording || state.wordCount > 0)
          Text(
            '${formatDuration(state.elapsed)} · ${state.wordCount} mots',
            style: theme.textTheme.labelMedium,
          ),
      ],
    );
  }
}

class _Controls extends ConsumerWidget {
  const _Controls({required this.state});

  final MeetingState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(meetingControllerProvider.notifier);

    if (state.phase == MeetingPhase.closed) {
      return FilledButton.tonal(
        onPressed: controller.reset,
        child: const Text('Nouvelle réunion'),
      );
    }
    if (state.phase == MeetingPhase.closing) {
      return const Row(
        children: [
          SizedBox(
            height: 16,
            width: 16,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          SizedBox(width: Space.md),
          Text('Compte rendu en cours…'),
        ],
      );
    }
    if (state.isRecording) {
      return FilledButton.icon(
        onPressed: controller.close,
        icon: const Icon(Icons.stop, size: 18),
        label: const Text('Terminer et produire le compte rendu'),
      );
    }
    return FilledButton.icon(
      key: const Key('meeting_start'),
      onPressed: () => controller.start(),
      icon: const Icon(Icons.mic, size: 18),
      label: Text(
        state.meeting == null ? 'Démarrer la réunion' : 'Reprendre la réunion',
      ),
    );
  }
}

class _Suggestions extends StatelessWidget {
  const _Suggestions({required this.state});

  final MeetingState state;

  @override
  Widget build(BuildContext context) {
    if (state.suggestions.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.lg),
        child: Text(
          state.isRecording
              // Deliberately not a spinner. Nothing is loading: the panel is
              // empty because nothing has been decided yet, and that is the
              // normal state of a meeting most of the time.
              ? 'Rien de net pour l\'instant. Les décisions et les actions '
                  'apparaîtront ici au fur et à mesure.'
              : 'Démarrez la réunion : les décisions, les actions et les '
                  'questions sans réponse seront relevées au fil de l\'eau.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      );
    }

    return Column(
      children: [
        for (final suggestion in state.suggestions)
          _SuggestionTile(
              key: ValueKey(suggestion.key), suggestion: suggestion),
      ],
    );
  }
}

class _SuggestionTile extends StatelessWidget {
  const _SuggestionTile({required this.suggestion, super.key});

  final MeetingSuggestion suggestion;

  IconData get _icon => switch (suggestion.kind) {
        SuggestionKind.action => Icons.check_circle_outline,
        SuggestionKind.decision => Icons.gavel_outlined,
        SuggestionKind.question => Icons.help_outline,
      };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: Space.sm),
      padding: const EdgeInsets.all(Space.md),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: Radii.mdAll,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(_icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: Space.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(suggestion.text, style: theme.textTheme.bodyMedium),
                const SizedBox(height: Space.xs),
                Row(
                  children: [
                    MfChip(label: suggestion.kind.label),
                    if (suggestion.owner != null) ...[
                      const SizedBox(width: Space.xs),
                      MfChip(
                          label: suggestion.owner!, icon: Icons.person_outline),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Report extends StatelessWidget {
  const _Report({required this.report});

  final MeetingReport report;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (report.degraded)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.md),
            child: MfNotice(
              icon: Icons.warning_amber_outlined,
              tone: MfNoticeTone.warning,
              message: report.reason.isEmpty
                  ? 'Compte rendu incomplet.'
                  : report.reason,
            ),
          ),
        if (report.summary.isNotEmpty) ...[
          const MfSectionHeader(title: 'Compte rendu'),
          Text(report.summary, style: theme.textTheme.bodyLarge),
        ],
        if (report.decisions.isNotEmpty) ...[
          const MfSectionHeader(title: 'Décisions'),
          for (final decision in report.decisions) _Line(text: decision),
        ],
        if (report.actions.isNotEmpty) ...[
          const MfSectionHeader(title: 'Actions'),
          for (final action in report.actions)
            _Line(
              text: action.text,
              detail: [
                if (action.owner != null) action.owner!,
                if (action.due != null) 'échéance ${action.due}',
              ].join(' · '),
            ),
        ],
        if (report.openQuestions.isNotEmpty) ...[
          const MfSectionHeader(title: 'Questions sans réponse'),
          for (final question in report.openQuestions) _Line(text: question),
        ],
        if (report.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: Space.md),
            // A meeting can genuinely produce nothing. Saying so is a correct
            // answer; inventing three sentences about it is not.
            child: Text(
              'Cette réunion n\'a produit aucune décision ni action.',
              style: theme.textTheme.bodySmall,
            ),
          ),
      ],
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.text, this.detail});

  final String text;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('— ', style: theme.textTheme.bodyMedium),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(text, style: theme.textTheme.bodyMedium),
                if (detail != null && detail!.isNotEmpty)
                  Text(detail!, style: theme.textTheme.labelSmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
