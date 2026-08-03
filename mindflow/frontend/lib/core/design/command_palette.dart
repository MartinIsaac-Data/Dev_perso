/// The command palette — ⌘K.
///
/// Borrowed wholesale from Raycast, because it solves a problem this product
/// acquires in phase 2: there are now a dozen screens, and a navigation bar with
/// a dozen entries is a navigation bar nobody reads. The palette makes the
/// number of screens irrelevant — you type what you want.
///
/// Three properties it has to have, and each is a decision:
///
/// * **It answers while you type.** Results are debounced by 180 ms and the
///   *previous* results stay on screen during the fetch. Clearing the list on
///   each keystroke makes the palette flicker, which reads as slowness even when
///   it is fast.
/// * **The keyboard is the primary input.** ↑ ↓ move, ↵ opens, Esc closes, and
///   the hints are visible. A palette you have to reach for the mouse in is
///   just a search box in a modal.
/// * **Commands rank above content.** Someone typing "cap" almost certainly
///   wants to *capture*, not to read a note containing "cap". Actions first,
///   then entries, then the rest.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/planning_models.dart';
import '../../features/planning/planning_providers.dart';
import 'components.dart';
import 'tokens.dart';

/// One row of the palette.
class PaletteAction {
  const PaletteAction({
    required this.id,
    required this.label,
    required this.icon,
    required this.onInvoke,
    this.hint,
    this.keywords = const [],
    this.shortcut = const [],
    this.group = 'Actions',
  });

  final String id;
  final String label;
  final IconData icon;
  final void Function(BuildContext context, WidgetRef ref) onInvoke;
  final String? hint;

  /// Alternative words that should match this action. "capturer" is found by
  /// "enregistrer", "micro" and "voix" — people do not all use the same noun.
  final List<String> keywords;
  final List<String> shortcut;
  final String group;

  bool matches(String query) {
    if (query.isEmpty) return true;
    final needle = query.toLowerCase();
    if (label.toLowerCase().contains(needle)) return true;
    return keywords.any((word) => word.toLowerCase().contains(needle));
  }
}

/// The static command list. Registered by the app shell so this file stays free
/// of route knowledge.
final paletteActionsProvider =
    StateProvider<List<PaletteAction>>((ref) => const []);

/// Whether the palette is open. A provider rather than local state so ⌘K works
/// from any screen and the palette can be opened programmatically (from an
/// empty state, say).
final paletteOpenProvider = StateProvider<bool>((ref) => false);

Future<void> showCommandPalette(BuildContext context, WidgetRef ref) async {
  if (ref.read(paletteOpenProvider)) return;
  ref.read(paletteOpenProvider.notifier).state = true;
  await showDialog<void>(
    context: context,
    barrierColor: Theme.of(context).colorScheme.scrim,
    builder: (context) => const _CommandPalette(),
  );
  if (context.mounted) {
    ref.read(paletteOpenProvider.notifier).state = false;
  }
}

class _CommandPalette extends ConsumerStatefulWidget {
  const _CommandPalette();

  @override
  ConsumerState<_CommandPalette> createState() => _CommandPaletteState();
}

class _CommandPaletteState extends ConsumerState<_CommandPalette> {
  final _controller = TextEditingController();
  final _focus = FocusNode();
  final _scroll = ScrollController();

  Timer? _debounce;
  String _query = '';
  String _debouncedQuery = '';
  int _selected = 0;

  @override
  void initState() {
    super.initState();
    // Focus on the next frame: requesting it during build fights the dialog's
    // own focus scope and loses about half the time.
    WidgetsBinding.instance.addPostFrameCallback((_) => _focus.requestFocus());
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    setState(() {
      _query = value;
      _selected = 0;
    });
    _debounce?.cancel();
    _debounce = Timer(Freshness.paletteDebounce, () {
      if (mounted) setState(() => _debouncedQuery = value.trim());
    });
  }

  List<_PaletteRow> _rows(List<PaletteAction> actions, QuickResults results) {
    final rows = <_PaletteRow>[];

    // Actions first: someone typing "cap" wants to capture, not to read a note
    // containing "cap".
    final matched = actions.where((action) => action.matches(_query)).toList();
    for (final action in matched) {
      rows.add(_PaletteRow.action(action));
    }
    for (final hit in results.entries) {
      rows.add(_PaletteRow.hit(hit, 'Notes'));
    }
    for (final hit in results.projects) {
      rows.add(_PaletteRow.hit(hit, 'Projets'));
    }
    for (final hit in results.tags) {
      rows.add(_PaletteRow.hit(hit, 'Tags'));
    }
    for (final hit in results.captures) {
      rows.add(_PaletteRow.hit(hit, 'Enregistrements'));
    }
    return rows;
  }

  void _move(int delta, int length) {
    if (length == 0) return;
    setState(() => _selected = (_selected + delta) % length);
    if (_selected < 0) _selected += length;
    // Keep the highlighted row on screen. Without this, arrowing past the fold
    // moves an invisible selection and ↵ opens something the user cannot see.
    const rowHeight = 44.0;
    final target =
        (_selected * rowHeight).clamp(0.0, _scroll.position.maxScrollExtent);
    _scroll.animateTo(target, duration: Motion.instant, curve: Motion.easeOut);
  }

  void _invoke(_PaletteRow row) {
    Navigator.of(context).pop();
    row.invoke(context, ref);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final actions = ref.watch(paletteActionsProvider);

    // The *previous* results stay visible while the next fetch is in flight:
    // clearing on each keystroke makes the palette flicker, which reads as
    // slowness even when it is fast.
    final results = ref.watch(quickSearchProvider(_debouncedQuery)).maybeWhen(
          data: (value) => value,
          orElse: () => const QuickResults(),
        );
    final rows = _rows(actions, results);
    final selected = rows.isEmpty ? 0 : _selected.clamp(0, rows.length - 1);

    return Dialog(
      alignment: Alignment.topCenter,
      insetPadding:
          const EdgeInsets.only(top: 96, left: Space.lg, right: Space.lg),
      backgroundColor: scheme.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: Radii.xlAll,
        side: BorderSide(color: scheme.outlineVariant),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 620, maxHeight: 460),
        child: Shortcuts(
          shortcuts: const {
            SingleActivator(LogicalKeyboardKey.arrowDown): _MoveIntent(1),
            SingleActivator(LogicalKeyboardKey.arrowUp): _MoveIntent(-1),
          },
          child: Actions(
            actions: {
              _MoveIntent: CallbackAction<_MoveIntent>(
                onInvoke: (intent) {
                  _move(intent.delta, rows.length);
                  return null;
                },
              ),
            },
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _SearchField(
                  controller: _controller,
                  focusNode: _focus,
                  onChanged: _onChanged,
                  onSubmit: () {
                    if (rows.isNotEmpty) _invoke(rows[selected]);
                  },
                ),
                const Divider(height: 1),
                Flexible(
                  child: rows.isEmpty
                      ? const _PaletteEmpty()
                      : _PaletteList(
                          rows: rows,
                          selected: selected,
                          controller: _scroll,
                          onHover: (index) => setState(() => _selected = index),
                          onInvoke: _invoke,
                        ),
                ),
                const Divider(height: 1),
                const _PaletteFooter(),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MoveIntent extends Intent {
  const _MoveIntent(this.delta);
  final int delta;
}

class _SearchField extends StatelessWidget {
  const _SearchField({
    required this.controller,
    required this.focusNode,
    required this.onChanged,
    required this.onSubmit,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final ValueChanged<String> onChanged;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
      child: Row(
        children: [
          Icon(Icons.search, size: 18, color: scheme.onSurfaceVariant),
          const SizedBox(width: Space.md),
          Expanded(
            child: TextField(
              key: const Key('palette_input'),
              controller: controller,
              focusNode: focusNode,
              onChanged: onChanged,
              onSubmitted: (_) => onSubmit(),
              textInputAction: TextInputAction.go,
              style: Theme.of(context).textTheme.bodyLarge,
              decoration: const InputDecoration(
                hintText: 'Rechercher ou lancer une action…',
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                filled: false,
                isDense: true,
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ),
          const MfKeyHint(['esc']),
        ],
      ),
    );
  }
}

class _PaletteList extends StatelessWidget {
  const _PaletteList({
    required this.rows,
    required this.selected,
    required this.controller,
    required this.onHover,
    required this.onInvoke,
  });

  final List<_PaletteRow> rows;
  final int selected;
  final ScrollController controller;
  final ValueChanged<int> onHover;
  final ValueChanged<_PaletteRow> onInvoke;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      controller: controller,
      padding: const EdgeInsets.symmetric(vertical: Space.sm),
      itemCount: rows.length,
      // Fixed extent: the palette can then compute its scroll geometry without
      // laying out the rows it is not showing.
      itemExtent: 44,
      itemBuilder: (context, index) {
        final row = rows[index];
        final showGroup = index == 0 || rows[index - 1].group != row.group;
        return _PaletteTile(
          row: row,
          selected: index == selected,
          showGroup: showGroup,
          onHover: () => onHover(index),
          onTap: () => onInvoke(row),
        );
      },
    );
  }
}

class _PaletteTile extends StatelessWidget {
  const _PaletteTile({
    required this.row,
    required this.selected,
    required this.showGroup,
    required this.onHover,
    required this.onTap,
  });

  final _PaletteRow row;
  final bool selected;
  final bool showGroup;
  final VoidCallback onHover;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return MouseRegion(
      onEnter: (_) => onHover(),
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: Space.sm, vertical: 1),
          padding: const EdgeInsets.symmetric(horizontal: Space.md),
          decoration: BoxDecoration(
            color: selected ? scheme.surfaceContainerHigh : Colors.transparent,
            borderRadius: Radii.mdAll,
          ),
          child: Row(
            children: [
              Icon(row.icon, size: 16, color: scheme.onSurfaceVariant),
              const SizedBox(width: Space.md),
              Expanded(
                child: Text(
                  row.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium,
                ),
              ),
              if (row.hint != null) ...[
                const SizedBox(width: Space.sm),
                Text(row.hint!, style: theme.textTheme.labelSmall),
              ],
              if (row.shortcut.isNotEmpty) ...[
                const SizedBox(width: Space.sm),
                MfKeyHint(row.shortcut),
              ] else if (showGroup) ...[
                const SizedBox(width: Space.sm),
                Text(row.group, style: theme.textTheme.labelSmall),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PaletteEmpty extends StatelessWidget {
  const _PaletteEmpty();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: Space.xxl),
      child: MfEmpty(
        icon: Icons.search_off,
        title: 'Aucun résultat',
        message: 'Essayez un autre mot, ou is:task, #tag, @projet.',
      ),
    );
  }
}

class _PaletteFooter extends StatelessWidget {
  const _PaletteFooter();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.sm),
      child: Row(
        children: [
          Text('Naviguer', style: theme.textTheme.labelSmall),
          const MfKeyHint(['↑', '↓']),
          const SizedBox(width: Space.lg),
          Text('Ouvrir', style: theme.textTheme.labelSmall),
          const MfKeyHint(['↵']),
          const Spacer(),
          Text('is:task  #tag  @projet  due:semaine',
              style: theme.textTheme.labelSmall),
        ],
      ),
    );
  }
}

/// A palette row is either a command or a search hit. Kept as one type so the
/// keyboard navigation does not have to care which is which.
class _PaletteRow {
  _PaletteRow.action(PaletteAction action)
      : label = action.label,
        icon = action.icon,
        hint = action.hint,
        shortcut = action.shortcut,
        group = action.group,
        _action = action,
        _hit = null;

  _PaletteRow.hit(QuickHit hit, this.group)
      : label = hit.title,
        icon = _iconForKind(hit.kind),
        hint = hit.subtitle,
        shortcut = const [],
        _action = null,
        _hit = hit;

  final String label;
  final IconData icon;
  final String? hint;
  final List<String> shortcut;
  final String group;
  final PaletteAction? _action;
  final QuickHit? _hit;

  void invoke(BuildContext context, WidgetRef ref) {
    final action = _action;
    if (action != null) {
      action.onInvoke(context, ref);
      return;
    }
    final hit = _hit;
    if (hit != null) {
      ref.read(paletteNavigationProvider)(context, hit);
    }
  }

  static IconData _iconForKind(String kind) => switch (kind) {
        'project' => Icons.folder_outlined,
        'tag' => Icons.sell_outlined,
        'capture' => Icons.graphic_eq,
        _ => Icons.subject,
      };
}

/// How to open a search hit. Injected by the shell so this file does not import
/// the router — the palette is a widget, not a navigator.
typedef PaletteNavigation = void Function(BuildContext context, QuickHit hit);

final paletteNavigationProvider = Provider<PaletteNavigation>(
  (ref) => (_, __) {},
);
