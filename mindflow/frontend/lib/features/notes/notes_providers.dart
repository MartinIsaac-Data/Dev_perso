/// Read models for the entry list and detail screens.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/client.dart';
import '../../core/api/models.dart';

/// Server-side filters. Held as a value object so the list provider has a single
/// dependency and rebuilds exactly once per filter change.
class NotesFilter {
  const NotesFilter({this.type, this.status, this.search = ''});

  /// Null means "every type" — the inbox view.
  final EntryType? type;
  final EntryStatus? status;
  final String search;

  NotesFilter copyWith({
    EntryType? type,
    EntryStatus? status,
    String? search,
    bool clearType = false,
    bool clearStatus = false,
  }) =>
      NotesFilter(
        type: clearType ? null : (type ?? this.type),
        status: clearStatus ? null : (status ?? this.status),
        search: search ?? this.search,
      );

  String? get typeParam => switch (type) {
        EntryType.task => 'task',
        EntryType.idea => 'idea',
        EntryType.note => 'note',
        EntryType.decision => 'decision',
        EntryType.question => 'question',
        EntryType.meeting => 'meeting',
        EntryType.reminder => 'reminder',
        _ => null,
      };

  String? get statusParam => switch (status) {
        EntryStatus.needsReview => 'needs_review',
        EntryStatus.active => 'active',
        EntryStatus.done => 'done',
        EntryStatus.archived => 'archived',
        EntryStatus.snoozed => 'snoozed',
        _ => null,
      };

  @override
  bool operator ==(Object other) =>
      other is NotesFilter &&
      other.type == type &&
      other.status == status &&
      other.search == search;

  @override
  int get hashCode => Object.hash(type, status, search);
}

final notesFilterProvider =
    StateProvider<NotesFilter>((ref) => const NotesFilter());

/// The list itself. `autoDispose` is deliberate: coming back to the list after
/// editing an entry elsewhere must show the edit, and the cheapest way to
/// guarantee that is not to cache across navigations.
final notesProvider = FutureProvider.autoDispose<List<Entry>>((ref) async {
  final filter = ref.watch(notesFilterProvider);
  return ref.watch(apiProvider).listEntries(
        entryType: filter.typeParam,
        status: filter.statusParam,
        search: filter.search,
      );
});

final entryProvider =
    FutureProvider.autoDispose.family<Entry, String>((ref, id) async {
  return ref.watch(apiProvider).getEntry(id);
});

final captureProvider =
    FutureProvider.autoDispose.family<Capture, String>((ref, id) async {
  return ref.watch(apiProvider).getCapture(id);
});

final capturesProvider = FutureProvider.autoDispose<List<Capture>>((ref) async {
  return ref.watch(apiProvider).listCaptures();
});

final dashboardProvider = FutureProvider.autoDispose<Dashboard>((ref) async {
  return ref.watch(apiProvider).dashboard();
});

/// Mutations. Kept out of the providers above so a write never has to know how
/// the read is cached — it invalidates and lets Riverpod refetch.
class EntryActions {
  const EntryActions(this._ref);

  final Ref _ref;

  MindflowApi get _api => _ref.read(apiProvider);

  void _invalidate() {
    _ref.invalidate(notesProvider);
    _ref.invalidate(dashboardProvider);
  }

  Future<Entry> toggleDone(Entry entry) async {
    final isDone = entry.status == EntryStatus.done;
    final updated = isDone
        ? await _api.updateEntry(
            entry.id,
            {'status': 'active'},
            expectedVersion: entry.version,
          )
        : await _api.completeEntry(entry.id);
    _invalidate();
    _ref.invalidate(entryProvider(entry.id));
    return updated;
  }

  /// A user edit is not just a text change: it makes the entry immune to being
  /// overwritten by a reprocessing run (ADR-027). The server sets that flag; the
  /// client only has to send the version it based its edit on.
  Future<Entry> edit(
    Entry entry, {
    String? title,
    String? body,
  }) async {
    final updated = await _api.updateEntry(
      entry.id,
      {
        if (title != null) 'title': title,
        if (body != null) 'body': body,
      },
      expectedVersion: entry.version,
    );
    _invalidate();
    _ref.invalidate(entryProvider(entry.id));
    return updated;
  }

  Future<void> delete(Entry entry) async {
    await _api.deleteEntry(entry.id);
    _invalidate();
  }

  Future<Entry> createNote({
    required String title,
    String entryType = 'note',
    String? dueExpression,
  }) async {
    final entry = await _api.createEntry(
      title: title,
      entryType: entryType,
      dueExpression: dueExpression,
    );
    _invalidate();
    return entry;
  }
}

final entryActionsProvider = Provider<EntryActions>(EntryActions.new);
