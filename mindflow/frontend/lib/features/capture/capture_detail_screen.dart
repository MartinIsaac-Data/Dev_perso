/// A capture, in full: the audio, the transcript, and what was extracted.
///
/// This screen is the product's audit trail. Anything MindFlow claims the user
/// said can be checked here against the recording itself, which is also why
/// deleting the audio does **not** delete the entries drawn from it (ADR-028) —
/// the two deletions answer different needs and are offered separately.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../core/api/client.dart';
import '../../core/api/errors.dart';
import '../../core/api/models.dart';
import '../../core/ui/formatting.dart';
import '../notes/entry_tile.dart';
import '../notes/notes_providers.dart';
import 'audio_player.dart';

class CaptureDetailScreen extends ConsumerWidget {
  const CaptureDetailScreen({required this.captureId, super.key});

  final String captureId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final capture = ref.watch(captureProvider(captureId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Enregistrement'),
        actions: [
          PopupMenuButton<String>(
            onSelected: (value) => _onAction(context, ref, value),
            itemBuilder: (context) => const [
              PopupMenuItem<String>(
                value: 'delete_audio',
                child: Text("Supprimer l'audio, garder les éléments"),
              ),
              PopupMenuItem<String>(
                value: 'delete_all',
                child: Text('Tout supprimer'),
              ),
            ],
          ),
        ],
      ),
      body: capture.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Text(
            error is ApiException ? error.userMessage : 'Introuvable.',
            textAlign: TextAlign.center,
          ),
        ),
        data: (value) => ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            Text(
              formatTimestamp(value.capturedAt),
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: 12),
            if (value.audioUrl != null)
              AudioPlayerBar(
                url: value.audioUrl!,
                // A fresh GET hands back a newly signed URL.
                onExpired: () => ref.invalidate(captureProvider(captureId)),
              )
            else
              const _Notice(
                icon: Icons.music_off_outlined,
                message: "L'audio n'est plus disponible.",
              ),
            const SizedBox(height: 20),
            _StatusNotice(capture: value),
            if (value.transcript != null) ...[
              const SizedBox(height: 8),
              Text(
                'Transcription',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 6),
              SelectableText(
                value.transcript!.text,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            ],
            if (value.entries.isNotEmpty) ...[
              const SizedBox(height: 24),
              Text(
                'Éléments extraits',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 4),
              for (final entry in value.entries)
                EntryTile(
                  entry: entry,
                  onTap: () => context.push(Routes.note(entry.id)),
                ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _onAction(
      BuildContext context, WidgetRef ref, String action) async {
    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final cascade = action == 'delete_all';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(cascade ? 'Tout supprimer ?' : "Supprimer l'audio ?"),
        content: Text(
          cascade
              ? "L'enregistrement et les éléments qui en sont issus seront supprimés."
              : "L'enregistrement sera supprimé. Les tâches, idées et notes qui en "
                  'sont issues seront conservées.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    );
    if (!(confirmed ?? false)) return;

    try {
      await ref.read(apiProvider).deleteCapture(captureId, cascade: cascade);
      ref
        ..invalidate(capturesProvider)
        ..invalidate(notesProvider)
        ..invalidate(dashboardProvider);
      navigator.pop();
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }
}

/// Says plainly where a capture stands when it did not go all the way through.
/// Every one of these states keeps the raw data (ADR-011): nothing the user
/// said is ever lost because a downstream stage failed.
class _StatusNotice extends StatelessWidget {
  const _StatusNotice({required this.capture});

  final Capture capture;

  @override
  Widget build(BuildContext context) {
    if (capture.isDegraded) {
      return const _Notice(
        icon: Icons.hourglass_bottom,
        message: 'Quota mensuel atteint : la transcription est disponible, '
            "l'analyse sera reprise plus tard.",
      );
    }
    return switch (capture.status) {
      CaptureStatus.transcriptionFailed => const _Notice(
          icon: Icons.error_outline,
          message:
              "La transcription a échoué. L'audio est conservé et sera retenté.",
        ),
      CaptureStatus.partiallyProcessed => const _Notice(
          icon: Icons.warning_amber_outlined,
          message:
              "La transcription est disponible ; l'analyse n'a pas abouti.",
        ),
      CaptureStatus.abandoned => const _Notice(
          icon: Icons.cancel_outlined,
          message: 'Cette capture a été abandonnée.',
        ),
      _ when !capture.status.isTerminal => const _Notice(
          icon: Icons.autorenew,
          message: 'Traitement en cours…',
        ),
      _ => const SizedBox.shrink(),
    };
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.secondaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icon, size: 18, color: scheme.onSecondaryContainer),
          const SizedBox(width: 10),
          Expanded(
            child: Text(message,
                style: TextStyle(color: scheme.onSecondaryContainer)),
          ),
        ],
      ),
    );
  }
}
