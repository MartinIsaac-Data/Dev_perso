/// Voice capture.
///
/// The screen has one job and shows one control. Everything the user needs to
/// trust it — that it is listening, for how long, and that the thought is safe —
/// is visible without reading a word.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../core/audio/recorder.dart';
import '../../core/ui/formatting.dart';
import '../notes/entry_tile.dart';
import '../notes/notes_providers.dart';
import 'capture_controller.dart';

class RecordScreen extends ConsumerStatefulWidget {
  const RecordScreen({super.key});

  @override
  ConsumerState<RecordScreen> createState() => _RecordScreenState();
}

class _RecordScreenState extends ConsumerState<RecordScreen> {
  /// Resolved once, in `initState`: reading a provider from `dispose` is not
  /// supported by Riverpod, and this is exactly where we need it.
  late final CaptureController _controller =
      ref.read(captureControllerProvider.notifier);

  @override
  void dispose() {
    // Leaving mid-recording must not leave the microphone open.
    if (_controller.isRecordingNow) {
      _controller.cancelRecording();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(captureControllerProvider);
    final controller = ref.read(captureControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Capturer'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Fermer',
          onPressed: () async {
            if (state.isRecording) await controller.cancelRecording();
            if (context.mounted) context.pop();
          },
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: switch (state.phase) {
            CapturePhase.idle ||
            CapturePhase.recording =>
              _Recorder(state: state),
            CapturePhase.sending ||
            CapturePhase.processing =>
              _Working(state: state),
            CapturePhase.done => _Result(state: state),
            CapturePhase.failed => _Failure(state: state),
          },
        ),
      ),
    );
  }
}

class _Recorder extends ConsumerWidget {
  const _Recorder({required this.state});

  final CaptureState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(captureControllerProvider.notifier);
    final theme = Theme.of(context);
    final recording = state.isRecording;
    final remaining = kMaxRecordingDuration - state.elapsed;

    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (state.message != null) ...[
          Text(
            state.message!,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 24),
        ],
        Text(
          recording ? formatDuration(state.elapsed) : '0:00',
          style: theme.textTheme.displaySmall
              ?.copyWith(fontWeight: FontWeight.w300),
        ),
        const SizedBox(height: 8),
        Text(
          recording
              ? (remaining.inSeconds <= 30
                  ? 'Limite dans ${remaining.inSeconds} s'
                  : 'Enregistrement en cours')
              : 'Appuyez et dites ce que vous avez en tête',
          style: theme.textTheme.bodyMedium
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 32),
        _Waveform(level: state.level, active: recording),
        const SizedBox(height: 40),
        _RecordButton(
          recording: recording,
          onPressed: () => recording
              ? controller.stopAndSend()
              : controller.startRecording(),
        ),
        const SizedBox(height: 24),
        SizedBox(
          height: 48,
          child: recording
              ? TextButton.icon(
                  onPressed: controller.cancelRecording,
                  icon: const Icon(Icons.delete_outline),
                  label: const Text('Annuler'),
                )
              : null,
        ),
      ],
    );
  }
}

class _RecordButton extends StatelessWidget {
  const _RecordButton({required this.recording, required this.onPressed});

  final bool recording;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      button: true,
      label:
          recording ? "Arrêter l'enregistrement" : 'Démarrer un enregistrement',
      child: GestureDetector(
        key: const Key('record_button'),
        onTap: onPressed,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          height: 96,
          width: 96,
          decoration: BoxDecoration(
            color: recording ? scheme.error : scheme.primary,
            shape: BoxShape.circle,
          ),
          child: Icon(
            recording ? Icons.stop : Icons.mic,
            size: 40,
            color: recording ? scheme.onError : scheme.onPrimary,
          ),
        ),
      ),
    );
  }
}

/// A level meter, not a real waveform: `record` reports a single amplitude per
/// tick, so drawing anything more detailed would be decoration pretending to be
/// data. Its only job is to prove the microphone is live.
class _Waveform extends StatelessWidget {
  const _Waveform({required this.level, required this.active});

  final double level;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // dBFS: -60 is silence, 0 is clipping.
    final normalised = ((level + 60) / 60).clamp(0.0, 1.0);
    return SizedBox(
      height: 64,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          for (var i = 0; i < 21; i++)
            AnimatedContainer(
              duration: const Duration(milliseconds: 120),
              margin: const EdgeInsets.symmetric(horizontal: 3),
              width: 4,
              height: active ? _barHeight(i, normalised) : 4,
              decoration: BoxDecoration(
                color: active ? scheme.primary : scheme.outlineVariant,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
        ],
      ),
    );
  }

  /// Tallest in the middle so the meter reads as a voice rather than a bar
  /// chart. Deterministic — a random shimmer would be a lie about the signal.
  double _barHeight(int index, double normalised) {
    final distance = (index - 10).abs() / 10;
    final envelope = 1 - (distance * distance);
    return 4 + (56 * normalised * envelope);
  }
}

class _Working extends StatelessWidget {
  const _Working({required this.state});

  final CaptureState state;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sending = state.phase == CapturePhase.sending;
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const CircularProgressIndicator(),
        const SizedBox(height: 28),
        Text(
          sending ? 'Envoi…' : 'Transcription et analyse…',
          style: theme.textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        Text(
          'Votre enregistrement est déjà en sécurité. '
          'Vous pouvez quitter cet écran.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        if (state.quotaWarning != null) ...[
          const SizedBox(height: 16),
          Text(
            state.quotaWarning!,
            textAlign: TextAlign.center,
            style: theme.textTheme.labelMedium
                ?.copyWith(color: theme.colorScheme.tertiary),
          ),
        ],
      ],
    );
  }
}

class _Result extends ConsumerWidget {
  const _Result({required this.state});

  final CaptureState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final capture = state.capture;
    final controller = ref.read(captureControllerProvider.notifier);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 8),
        Row(
          children: [
            Icon(Icons.check_circle, color: theme.colorScheme.primary),
            const SizedBox(width: 10),
            Expanded(
              child: Text('Capture enregistrée',
                  style: theme.textTheme.titleMedium),
            ),
          ],
        ),
        if (state.message != null) ...[
          const SizedBox(height: 12),
          Text(
            state.message!,
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ],
        if (capture?.transcript != null) ...[
          const SizedBox(height: 20),
          Text('Ce que vous avez dit', style: theme.textTheme.labelLarge),
          const SizedBox(height: 6),
          Text(capture!.transcript!.text, style: theme.textTheme.bodyMedium),
        ],
        if (capture != null && capture.entries.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text('Ce que nous en avons tiré', style: theme.textTheme.labelLarge),
          const SizedBox(height: 4),
          Expanded(
            child: ListView(
              children: [
                for (final entry in capture.entries)
                  EntryTile(
                    entry: entry,
                    onTap: () => context.push(Routes.note(entry.id)),
                  ),
              ],
            ),
          ),
        ] else
          const Spacer(),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: () {
                  controller.reset();
                  ref.invalidate(notesProvider);
                  ref.invalidate(dashboardProvider);
                  context.pop();
                },
                child: const Text('Terminer'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                onPressed: controller.reset,
                child: const Text('Capturer à nouveau'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _Failure extends ConsumerWidget {
  const _Failure({required this.state});

  final CaptureState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final controller = ref.read(captureControllerProvider.notifier);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(Icons.cloud_off_outlined,
            size: 44, color: theme.colorScheme.outline),
        const SizedBox(height: 16),
        Text(
          state.message ?? "L'envoi a échoué.",
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: controller.flushPending,
          child: const Text('Réessayer maintenant'),
        ),
        const SizedBox(height: 8),
        TextButton(
          onPressed: () {
            controller.reset();
            context.pop();
          },
          child: const Text('Plus tard'),
        ),
      ],
    );
  }
}
