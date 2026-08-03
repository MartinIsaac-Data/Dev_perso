/// The conversational assistant.
///
/// Borrowed from ChatGPT, and only the parts that are actually good: a bounded
/// reading column whatever the window width, an answer that appears as it is
/// written, and a composer that stays where the eye already is. Everything else
/// follows the Linear-ish restraint of the rest of the product — no avatars, no
/// bubbles with tails, no gradients.
///
/// Two things here are product decisions rather than styling:
///
/// * **Citations are rendered under every generated answer.** An answer whose
///   sources are invisible is indistinguishable from one that was invented, and
///   the reader has no way to tell which they are looking at. Structured
///   answers — today's agenda, overdue tasks — show none, because they have
///   none to show and an empty "sources" strip would read as a failure.
/// * **The plan is shown.** « Réponse construite depuis vos échéances, sans
///   modèle de langage » is a sentence that lets a user calibrate their trust,
///   and lets them notice when the assistant has misread the question.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/assistant_models.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import 'assistant_providers.dart';

class AssistantScreen extends ConsumerStatefulWidget {
  const AssistantScreen({super.key});

  @override
  ConsumerState<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends ConsumerState<AssistantScreen> {
  final _composer = TextEditingController();
  final _scroll = ScrollController();
  final _focus = FocusNode();

  @override
  void dispose() {
    _composer.dispose();
    _scroll.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _send([String? preset]) async {
    final question = preset ?? _composer.text;
    if (question.trim().isEmpty) return;
    _composer.clear();
    _focus.requestFocus();

    await ref.read(chatControllerProvider.notifier).ask(question);
    _scrollToEnd();
  }

  void _scrollToEnd() {
    // Post-frame, because the new message has not been laid out yet when the
    // state changes — jumping now would scroll to the old extent.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: Motion.normal,
        curve: Motion.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(chatControllerProvider);
    ref.listen(chatControllerProvider, (previous, next) {
      if (previous?.messages.length != next.messages.length) _scrollToEnd();
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('Assistant'),
        actions: [
          IconButton(
            onPressed: state.isEmpty
                ? null
                : () => ref.read(chatControllerProvider.notifier).reset(),
            icon: const Icon(Icons.add_comment_outlined),
            tooltip: 'Nouvelle conversation',
          ),
        ],
      ),
      body: Column(
        children: [
          if (state.error != null)
            Padding(
              padding: const EdgeInsets.all(Space.md),
              child: MfNotice(
                icon: Icons.error_outline,
                message: state.error!,
                tone: MfNoticeTone.danger,
              ),
            ),
          Expanded(
            child: state.isEmpty
                ? _Suggestions(onPick: _send)
                : _Transcript(scroll: _scroll, messages: state.messages),
          ),
          _Composer(
            controller: _composer,
            focusNode: _focus,
            sending: state.sending,
            onSend: _send,
          ),
        ],
      ),
    );
  }
}

/// The empty state: the five questions the product is built to answer.
///
/// A blank chat box is the hardest interface in software to start using. These
/// say what kind of thing this assistant is for far faster than placeholder
/// text ever could.
class _Suggestions extends StatelessWidget {
  const _Suggestions({required this.onPick});

  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MfContentColumn(
      child: ListView(
        padding: const EdgeInsets.symmetric(vertical: Space.xxl),
        children: [
          Text('Posez une question sur vos notes',
              style: theme.textTheme.titleLarge),
          const SizedBox(height: Space.sm),
          Text(
            'Les réponses sont construites à partir de vos captures, et citent '
            'toujours ce sur quoi elles s\'appuient.',
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: Space.xl),
          for (final question in suggestedQuestions)
            Padding(
              padding: const EdgeInsets.only(bottom: Space.sm),
              child: _SuggestionTile(
                  question: question, onTap: () => onPick(question)),
            ),
        ],
      ),
    );
  }
}

class _SuggestionTile extends StatelessWidget {
  const _SuggestionTile({required this.question, required this.onTap});

  final String question;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surfaceContainerLow,
      borderRadius: Radii.mdAll,
      child: InkWell(
        onTap: onTap,
        borderRadius: Radii.mdAll,
        child: Padding(
          padding: const EdgeInsets.symmetric(
              horizontal: Space.md, vertical: Space.md),
          child: Row(
            children: [
              Icon(Icons.auto_awesome_outlined,
                  size: 16, color: scheme.onSurfaceVariant),
              const SizedBox(width: Space.md),
              Expanded(
                child: Text(question,
                    style: Theme.of(context).textTheme.bodyMedium),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Transcript extends StatelessWidget {
  const _Transcript({required this.scroll, required this.messages});

  final ScrollController scroll;
  final List<ChatMessage> messages;

  @override
  Widget build(BuildContext context) {
    return MfContentColumn(
      child: ListView.builder(
        controller: scroll,
        padding: const EdgeInsets.symmetric(vertical: Space.lg),
        itemCount: messages.length,
        // Keyed by identity so a rebuild reuses the element rather than
        // re-creating every bubble on each streamed fragment.
        findChildIndexCallback: (key) {
          final value = (key as ValueKey<String>).value;
          final index = messages.indexWhere((m) => m.id == value);
          return index < 0 ? null : index;
        },
        itemBuilder: (context, index) {
          final message = messages[index];
          return RepaintBoundary(
            key: ValueKey(message.id),
            child: _MessageBlock(message: message),
          );
        },
      ),
    );
  }
}

class _MessageBlock extends StatelessWidget {
  const _MessageBlock({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    if (message.isUser) {
      // The question sits right-aligned in a tinted block. Deliberately the
      // only tinted surface in the transcript: the reader's eye needs one cue
      // to find where they asked, and the answers are what they came to read.
      return Padding(
        padding: const EdgeInsets.only(bottom: Space.lg),
        child: Align(
          alignment: Alignment.centerRight,
          child: Container(
            constraints: const BoxConstraints(maxWidth: 520),
            padding: const EdgeInsets.symmetric(
                horizontal: Space.md, vertical: Space.sm),
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHigh,
              borderRadius: Radii.lgAll,
            ),
            child: Text(message.content, style: theme.textTheme.bodyMedium),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: Space.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (message.content.isEmpty && message.pending)
            const _Thinking()
          else
            SelectableText(
              message.content,
              // Generous leading: an answer is prose and should read like it
              // (the Notion half of the design language).
              style: theme.textTheme.bodyLarge?.copyWith(height: 1.55),
            ),
          if (message.citations.isNotEmpty) ...[
            const SizedBox(height: Space.md),
            _Citations(citations: message.citations),
          ],
        ],
      ),
    );
  }
}

/// Three dots. Shown only while an answer is genuinely being written — the
/// structured routes have nothing to wait for and never reach this.
class _Thinking extends StatefulWidget {
  const _Thinking();

  @override
  State<_Thinking> createState() => _ThinkingState();
}

class _ThinkingState extends State<_Thinking>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colour = Theme.of(context).colorScheme.onSurfaceVariant;
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var index = 0; index < 3; index++)
              Padding(
                padding: const EdgeInsets.only(right: Space.xs),
                child: _Dot(
                  // Staggered so the row reads as motion rather than as a
                  // flashing block.
                  opacity: _phase(index),
                  colour: colour,
                ),
              ),
          ],
        );
      },
    );
  }

  double _phase(int index) {
    final shifted = (_controller.value + index * 0.2) % 1.0;
    return 0.3 + 0.7 * (shifted < 0.5 ? shifted * 2 : (1 - shifted) * 2);
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.opacity, required this.colour});

  final double opacity;
  final Color colour;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 6,
      height: 6,
      decoration: BoxDecoration(
        // `withValues` on the colour rather than an `Opacity` widget: a
        // per-dot opacity layer costs a saveLayer on every frame.
        color: colour.withValues(alpha: opacity),
        shape: BoxShape.circle,
      ),
    );
  }
}

class _Citations extends StatelessWidget {
  const _Citations({required this.citations});

  final List<Citation> citations;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          citations.length == 1 ? 'Source' : 'Sources',
          style: theme.textTheme.labelSmall
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: Space.sm),
        Wrap(
          spacing: Space.sm,
          runSpacing: Space.sm,
          children: [
            for (var index = 0; index < citations.length; index++)
              _CitationChip(index: index + 1, citation: citations[index]),
          ],
        ),
      ],
    );
  }
}

class _CitationChip extends StatelessWidget {
  const _CitationChip({required this.index, required this.citation});

  final int index;
  final Citation citation;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Tooltip(
      message: citation.excerpt,
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: Space.sm, vertical: Space.xs),
        decoration: BoxDecoration(
          borderRadius: Radii.smAll,
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('[$index]',
                style: theme.textTheme.labelSmall
                    ?.copyWith(color: scheme.primary)),
            const SizedBox(width: Space.xs),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 220),
              child: Text(
                citation.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.labelSmall,
              ),
            ),
            if (citation.occurredAt != null) ...[
              const SizedBox(width: Space.xs),
              Text(
                citation.occurredAt!,
                style: theme.textTheme.labelSmall
                    ?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.focusNode,
    required this.sending,
    required this.onSend,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool sending;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      top: false,
      child: MfContentColumn(
        padding: const EdgeInsets.fromLTRB(Space.lg, 0, Space.lg, Space.lg),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Shortcuts(
                shortcuts: const {
                  // Enter sends, Shift+Enter breaks the line. The convention
                  // every chat interface has converged on, and getting it
                  // backwards is instantly infuriating.
                  SingleActivator(LogicalKeyboardKey.enter): _SendIntent(),
                },
                child: Actions(
                  actions: {
                    _SendIntent: CallbackAction<_SendIntent>(
                      onInvoke: (_) {
                        if (!sending) onSend();
                        return null;
                      },
                    ),
                  },
                  child: TextField(
                    controller: controller,
                    focusNode: focusNode,
                    minLines: 1,
                    maxLines: 6,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => sending ? null : onSend(),
                    decoration: InputDecoration(
                      hintText: 'Posez une question sur vos notes…',
                      filled: true,
                      fillColor: scheme.surfaceContainerLow,
                      border: const OutlineInputBorder(
                        borderRadius: Radii.lgAll,
                        borderSide: BorderSide.none,
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: Space.md, vertical: Space.md),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: Space.sm),
            IconButton.filled(
              onPressed: sending ? null : onSend,
              icon: sending
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.arrow_upward),
              tooltip: 'Envoyer',
            ),
          ],
        ),
      ),
    );
  }
}

class _SendIntent extends Intent {
  const _SendIntent();
}
