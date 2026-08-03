/// `AgendaQuery` is the cache key of the agenda family provider.
///
/// If its equality is wrong, every rebuild mints a new provider and the screen
/// refetches on each frame — a bug that looks like "the agenda is slow" and is
/// actually "the agenda is fetched sixty times a second".
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/planning_models.dart';
import 'package:mindflow/features/planning/planning_providers.dart';

void main() {
  group('equality', () {
    test('two identical queries are equal and hash alike', () {
      final anchor = DateTime(2026, 6, 10, 14, 30);
      final first = AgendaQuery(view: AgendaView.week, anchor: anchor);
      final second = AgendaQuery(view: AgendaView.week, anchor: anchor);

      expect(first, second);
      expect(first.hashCode, second.hashCode);
    });

    test('anchors within the same day describe the same window', () {
      // Normalising to the day is what keeps the cache useful: two rebuilds a
      // second apart must not be two different windows.
      final morning = AgendaQuery(anchor: DateTime(2026, 6, 10, 8));
      final evening = AgendaQuery(anchor: DateTime(2026, 6, 10, 22));

      expect(morning, evening);
      expect(morning.hashCode, evening.hashCode);
    });

    test('a different day is a different query', () {
      expect(
        AgendaQuery(anchor: DateTime(2026, 6, 10)),
        isNot(AgendaQuery(anchor: DateTime(2026, 6, 11))),
      );
    });

    test('every facet participates in identity', () {
      const base = AgendaQuery();
      expect(base, isNot(base.copyWith(view: AgendaView.day)));
      expect(base, isNot(base.copyWith(includeDone: false)));
      expect(base, isNot(base.copyWith(includeUnscheduled: true)));
      expect(base, isNot(base.copyWith(projectId: 'p1')));
    });

    test('a null anchor is distinct from a set one', () {
      expect(const AgendaQuery(),
          isNot(AgendaQuery(anchor: DateTime(2026, 6, 10))));
    });
  });

  group('copyWith', () {
    test('changes one facet and leaves the rest', () {
      final original = AgendaQuery(
        view: AgendaView.month,
        anchor: DateTime(2026, 6, 10),
        includeDone: false,
        projectId: 'p1',
      );

      final updated = original.copyWith(view: AgendaView.day);

      expect(updated.view, AgendaView.day);
      expect(updated.includeDone, isFalse);
      expect(updated.projectId, 'p1');
    });

    test('clears the project explicitly', () {
      // A nullable field cannot be cleared by passing null — that is
      // indistinguishable from "unchanged" — so clearing is its own flag.
      const original = AgendaQuery(projectId: 'p1');
      expect(original.copyWith(clearProject: true).projectId, isNull);
      expect(original.copyWith().projectId, 'p1');
    });
  });

  group('AgendaView', () {
    test('serialises to the wire value the API expects', () {
      expect(AgendaView.day.param, 'day');
      expect(AgendaView.week.param, 'week');
      expect(AgendaView.month.param, 'month');
    });

    test('has a French label for the switcher', () {
      expect(AgendaView.week.label, 'Semaine');
    });
  });
}
