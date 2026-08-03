/// Playback of a capture's original audio.
///
/// The URL is a short-lived signed link handed out by the API; the bytes come
/// straight from object storage and never transit the backend (ADR-018). That
/// has a consequence this widget has to handle: the link expires, and an
/// expired link fails at *play* time, not at load time. So a playback error is
/// reported as "lien expiré, rechargez" rather than as a broken recording.
library;

import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import '../../core/ui/formatting.dart';

class AudioPlayerBar extends StatefulWidget {
  const AudioPlayerBar({
    required this.url,
    this.onExpired,
    super.key,
  });

  final String url;

  /// Called when the source can no longer be loaded, so the caller can ask the
  /// API for a fresh signed URL.
  final VoidCallback? onExpired;

  @override
  State<AudioPlayerBar> createState() => _AudioPlayerBarState();
}

class _AudioPlayerBarState extends State<AudioPlayerBar> {
  final _player = AudioPlayer();
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(AudioPlayerBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url) _load();
  }

  Future<void> _load() async {
    setState(() => _failed = false);
    try {
      await _player.setUrl(widget.url);
    } on PlayerException {
      if (mounted) setState(() => _failed = true);
    } on PlayerInterruptedException {
      // Superseded by another load; the newer one owns the state.
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_failed) {
      return Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            const Icon(Icons.link_off, size: 18),
            const SizedBox(width: 10),
            const Expanded(child: Text('Lien de lecture expiré.')),
            TextButton(
              onPressed: widget.onExpired ?? _load,
              child: const Text('Recharger'),
            ),
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(16),
      ),
      child: StreamBuilder<PlayerState>(
        stream: _player.playerStateStream,
        builder: (context, snapshot) {
          final playerState = snapshot.data;
          final processing = playerState?.processingState;
          final playing = playerState?.playing ?? false;
          final loading = processing == ProcessingState.loading ||
              processing == ProcessingState.buffering;

          return Row(
            children: [
              IconButton(
                key: const Key('audio_play'),
                iconSize: 36,
                tooltip: playing ? 'Pause' : 'Lire',
                onPressed: loading
                    ? null
                    : () {
                        if (processing == ProcessingState.completed) {
                          _player.seek(Duration.zero);
                        }
                        playing ? _player.pause() : _player.play();
                      },
                icon: Icon(
                  loading
                      ? Icons.hourglass_empty
                      : playing
                          ? Icons.pause_circle_filled
                          : Icons.play_circle_fill,
                ),
              ),
              Expanded(
                child: StreamBuilder<Duration>(
                  stream: _player.positionStream,
                  builder: (context, positionSnapshot) {
                    final total = _player.duration ?? Duration.zero;
                    final position = positionSnapshot.data ?? Duration.zero;
                    final max = total.inMilliseconds.toDouble();
                    final value = position.inMilliseconds
                        .clamp(0, total.inMilliseconds)
                        .toDouble();
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SliderTheme(
                          data: SliderTheme.of(context).copyWith(
                            trackHeight: 3,
                            thumbShape: const RoundSliderThumbShape(
                                enabledThumbRadius: 6),
                            overlayShape: const RoundSliderOverlayShape(
                                overlayRadius: 12),
                          ),
                          child: Slider(
                            value: value,
                            max: max <= 0 ? 1 : max,
                            onChanged: max <= 0
                                ? null
                                : (next) => _player
                                    .seek(Duration(milliseconds: next.round())),
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 12),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                formatDuration(position),
                                style: theme.textTheme.labelSmall,
                              ),
                              Text(
                                formatDuration(total),
                                style: theme.textTheme.labelSmall,
                              ),
                            ],
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
