/// Minting a share link, and showing it exactly once.
///
/// The whole design of this sheet follows from one server-side fact: only a
/// SHA-256 digest of the token is stored, so the plaintext exists for the
/// duration of one response and can never be produced again.
///
/// Hence: the link is displayed large, with a copy button, and the sheet says
/// plainly that it will not be shown again. A product that quietly relied on
/// the user noticing would be one where people lose links and blame themselves.
///
/// Expiry defaults to thirty days rather than "never" because a security
/// setting somebody has to remember to switch on only protects the people who
/// did not need it.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/enterprise_models.dart';
import '../../core/api/errors.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import 'enterprise_providers.dart';
import 'enterprise_ui.dart';

/// Expiry choices. « Jamais » is present but last, and is not the default.
enum ShareDuration {
  week,
  month,
  quarter,
  never;

  String get label => switch (this) {
        ShareDuration.week => '7 jours',
        ShareDuration.month => '30 jours',
        ShareDuration.quarter => '90 jours',
        ShareDuration.never => 'Jamais',
      };

  Duration? get value => switch (this) {
        ShareDuration.week => const Duration(days: 7),
        ShareDuration.month => const Duration(days: 30),
        ShareDuration.quarter => const Duration(days: 90),
        ShareDuration.never => null,
      };
}

Future<void> showShareSheet(BuildContext context, String entryId) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => ShareSheet(entryId: entryId),
  );
}

class ShareSheet extends ConsumerStatefulWidget {
  const ShareSheet({required this.entryId, super.key});

  final String entryId;

  @override
  ConsumerState<ShareSheet> createState() => _ShareSheetState();
}

class _ShareSheetState extends ConsumerState<ShareSheet> {
  ShareDuration _duration = ShareDuration.month;
  bool _allowComments = false;
  bool _minting = false;
  ShareLink? _issued;

  /// Captured while the widget is alive.
  ///
  /// `ref` reads the element's context, which is gone by the time `dispose`
  /// runs — and deferring the read to a microtask does not help, because the
  /// State is already defunct when it fires. Holding the controller is the only
  /// way to clear the plaintext *as the sheet closes*, which is the behaviour
  /// that matters: the token must not outlive the screen that showed it.
  StateController<ShareLink?>? _issuedController;

  @override
  void initState() {
    super.initState();
    _issuedController = ref.read(issuedShareProvider.notifier);
  }

  @override
  void dispose() {
    // The plaintext dies with the sheet, which is the truth of the matter.
    _issuedController?.state = null;
    super.dispose();
  }

  Future<void> _mint() async {
    setState(() => _minting = true);
    try {
      final expiry = _duration.value;
      final link = await ref.read(enterpriseActionsProvider).share(
            widget.entryId,
            expiresAt:
                expiry == null ? null : DateTime.now().toUtc().add(expiry),
            allowComments: _allowComments,
          );
      if (mounted) setState(() => _issued = link);
    } on ApiException catch (error) {
      if (mounted) showErrorSnack(context, error);
    } finally {
      if (mounted) setState(() => _minting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final link = _issued;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(Space.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Partager cette note', style: theme.textTheme.titleMedium),
            const SizedBox(height: Space.sm),
            if (link == null) ...[
              Text(
                'Un lien de partage donne accès à cette note, en lecture, '
                'à qui le possède.',
                style: theme.textTheme.bodySmall,
              ),
              const MfSectionHeader(title: 'Expiration'),
              Wrap(
                spacing: Space.sm,
                children: [
                  for (final duration in ShareDuration.values)
                    MfChip(
                      label: duration.label,
                      selected: _duration == duration,
                      onTap: () => setState(() => _duration = duration),
                    ),
                ],
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _allowComments,
                onChanged: (value) => setState(() => _allowComments = value),
                title: const Text('Autoriser les commentaires'),
              ),
              const SizedBox(height: Space.md),
              FilledButton(
                onPressed: _minting ? null : _mint,
                child: const Text('Créer le lien'),
              ),
            ] else
              _IssuedLink(link: link),
          ],
        ),
      ),
    );
  }
}

class _IssuedLink extends StatelessWidget {
  const _IssuedLink({required this.link});

  final ShareLink link;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final token = link.token ?? '';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const MfNotice(
          icon: Icons.warning_amber_outlined,
          tone: MfNoticeTone.warning,
          message:
              'Ce lien n\'est affiché qu\'une fois. Copiez-le maintenant : '
              'il n\'est pas stocké et ne peut pas être réaffiché.',
        ),
        const SizedBox(height: Space.md),
        SelectableText(
          token,
          style: theme.textTheme.bodyMedium
              ?.copyWith(fontFamily: 'monospace', height: 1.5),
        ),
        const SizedBox(height: Space.md),
        Row(
          children: [
            FilledButton.icon(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: token));
                if (context.mounted) showMessage(context, 'Lien copié.');
              },
              icon: const Icon(Icons.copy, size: 16),
              label: const Text('Copier'),
            ),
            const Spacer(),
            if (link.expiresAt != null)
              Text(
                'Expire ${formatDay(link.expiresAt!)}',
                style: theme.textTheme.bodySmall,
              ),
          ],
        ),
      ],
    );
  }
}
