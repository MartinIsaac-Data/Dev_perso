"""The search query language.

Two rules dominate these tests, because both are about not being hostile to the
person typing: an unrecognised token is free text rather than an error, and a
filter *value* that names nothing is reported rather than guessed at.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.enums import EntryStatus, EntryType, Priority
from app.domain.search_query import parse_query, to_websearch

PARIS = "Europe/Paris"
NOW = datetime(2026, 6, 10, 14, 30, tzinfo=ZoneInfo(PARIS))  # a Wednesday


class TestFreeText:
    def test_plain_words_stay_free_text(self) -> None:
        parsed = parse_query("réunion budget DAF", now=NOW, timezone=PARIS)
        assert parsed.text == "réunion budget DAF"
        assert not parsed.has_filters

    def test_a_quoted_phrase_survives_as_one_term(self) -> None:
        parsed = parse_query('"appel du lundi" urgent', now=NOW, timezone=PARIS)
        assert "appel du lundi" in parsed.text

    def test_an_unrecognised_colon_token_is_free_text_not_an_error(self) -> None:
        """Somebody typing "budget: 3000" is searching, not writing a filter.

        A search box that rejects input is a search box people stop using.
        """
        parsed = parse_query("budget: 3000", now=NOW, timezone=PARIS)
        assert "3000" in parsed.text
        assert parsed.ignored == []

    def test_an_empty_query_is_empty(self) -> None:
        assert parse_query("", now=NOW, timezone=PARIS).is_empty
        assert parse_query("   ", now=NOW, timezone=PARIS).is_empty


class TestFilters:
    def test_is_accepts_a_type(self) -> None:
        parsed = parse_query("is:task", now=NOW, timezone=PARIS)
        assert parsed.types == [EntryType.TASK]

    def test_is_accepts_a_status_on_the_same_prefix(self) -> None:
        """Users do not hold the type/status distinction in their heads, and
        both readings are unambiguous here."""
        parsed = parse_query("is:done", now=NOW, timezone=PARIS)
        assert parsed.statuses == [EntryStatus.DONE]

    def test_accepts_french_aliases(self) -> None:
        parsed = parse_query("is:tâche p:urgente", now=NOW, timezone=PARIS)
        assert parsed.types == [EntryType.TASK]
        assert parsed.priorities == [Priority.URGENT]

    def test_repeating_a_filter_widens_rather_than_replaces(self) -> None:
        """`is:task is:idea` means either — what the same syntax means in every
        tool the user has already learned."""
        parsed = parse_query("is:task is:idea", now=NOW, timezone=PARIS)
        assert parsed.types == [EntryType.TASK, EntryType.IDEA]

    def test_hash_and_at_shorthands(self) -> None:
        parsed = parse_query("#Finance @refonte", now=NOW, timezone=PARIS)
        assert parsed.tags == ["finance"]
        assert parsed.projects == ["refonte"]

    def test_flags(self) -> None:
        parsed = parse_query("is:overdue is:recurring is:pinned", now=NOW, timezone=PARIS)
        assert parsed.overdue and parsed.recurring and parsed.pinned

    def test_reports_a_value_it_cannot_map_instead_of_guessing(self) -> None:
        """`p:hgih` filters on nothing and says so — it does not become `high`."""
        parsed = parse_query("p:hgih", now=NOW, timezone=PARIS)
        assert parsed.priorities == []
        assert parsed.ignored == ["p:hgih"]

    def test_mixes_text_and_filters(self) -> None:
        parsed = parse_query("DAF is:task p:high #finance", now=NOW, timezone=PARIS)
        assert parsed.text == "DAF"
        assert parsed.types == [EntryType.TASK]
        assert parsed.priorities == [Priority.HIGH]
        assert parsed.tags == ["finance"]


class TestDateWindows:
    def test_today_is_a_window_not_an_instant(self) -> None:
        """`due:today` must include everything due today, not everything due at
        this exact second."""
        parsed = parse_query("due:today", now=NOW, timezone=PARIS)
        assert parsed.due is not None
        assert parsed.due.start is not None and parsed.due.end is not None
        assert parsed.due.start.astimezone(ZoneInfo(PARIS)).hour == 0
        assert (parsed.due.end - parsed.due.start).days == 1

    def test_week_starts_on_monday(self) -> None:
        parsed = parse_query("due:semaine", now=NOW, timezone=PARIS)
        assert parsed.due is not None and parsed.due.start is not None
        assert parsed.due.start.astimezone(ZoneInfo(PARIS)).day == 8  # Monday

    def test_month_spans_the_calendar_month(self) -> None:
        parsed = parse_query("due:mois", now=NOW, timezone=PARIS)
        assert parsed.due is not None
        assert parsed.due.start is not None and parsed.due.end is not None
        assert parsed.due.start.astimezone(ZoneInfo(PARIS)).day == 1
        assert parsed.due.end.astimezone(ZoneInfo(PARIS)).month == 7

    def test_overdue_window_is_bounded_only_above(self) -> None:
        parsed = parse_query("due:retard", now=NOW, timezone=PARIS)
        assert parsed.due is not None
        assert parsed.due.start is None
        assert parsed.due.end is not None

    def test_due_none_is_present_but_unbounded(self) -> None:
        """Distinguished from a missing filter by being present-and-empty: it
        means "no due date", which is a real thing to search for."""
        parsed = parse_query("due:none", now=NOW, timezone=PARIS)
        assert parsed.due is not None
        assert not parsed.due.bounded

    @pytest.mark.parametrize("value", ["2026-06-12", "12/06/2026"])
    def test_explicit_dates(self, value: str) -> None:
        parsed = parse_query(f"due:{value}", now=NOW, timezone=PARIS)
        assert parsed.due is not None and parsed.due.start is not None
        assert parsed.due.start.astimezone(ZoneInfo(PARIS)).day == 12

    def test_an_unparseable_date_is_reported(self) -> None:
        parsed = parse_query("due:someday", now=NOW, timezone=PARIS)
        assert parsed.due is None
        assert parsed.ignored == ["due:someday"]

    def test_windows_use_the_user_zone_not_utc(self) -> None:
        """At 00:30 in Paris it is still the previous day in UTC. The window has
        to follow the user's calendar, or an agenda is wrong for an hour every
        night and a whole hour twice a year."""
        midnight_paris = datetime(2026, 6, 11, 0, 30, tzinfo=ZoneInfo(PARIS))
        parsed = parse_query("due:today", now=midnight_paris, timezone=PARIS)
        assert parsed.due is not None and parsed.due.start is not None
        assert parsed.due.start.astimezone(ZoneInfo(PARIS)).day == 11
        assert parsed.due.start.astimezone(UTC).day == 10


class TestWebsearchPreparation:
    def test_collapses_whitespace_and_caps_length(self) -> None:
        assert to_websearch("  a   b  ") == "a b"
        assert len(to_websearch("x" * 500)) == 200

    def test_leaves_operators_alone(self) -> None:
        """`websearch_to_tsquery` understands quotes, `or` and `-exclusion`, and
        — the reason it is used at all — never raises on malformed input."""
        assert to_websearch('"exact phrase" or -excluded') == '"exact phrase" or -excluded'
