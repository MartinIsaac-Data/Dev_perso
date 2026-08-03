"""Recurrence: parsing, and computing the next occurrence.

The properties under test are the ones a user would notice being wrong:
a schedule that drifts, a schedule that produces a pile of overdue copies, and a
monthly task that walks through the calendar.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.domain.recurrence import RecurrenceRule, next_occurrence, parse


class TestParse:
    def test_reads_the_supported_subset(self) -> None:
        rule = parse("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH;COUNT=10")
        assert rule == RecurrenceRule(frequency="WEEKLY", interval=2, by_weekday=(0, 3), count=10)

    def test_tolerates_the_rrule_prefix_and_case(self) -> None:
        assert parse("RRULE:freq=daily") == RecurrenceRule(frequency="DAILY")

    def test_reads_until(self) -> None:
        rule = parse("FREQ=DAILY;UNTIL=20260901")
        assert rule is not None
        assert rule.until == date(2026, 9, 1)

    @pytest.mark.parametrize(
        "rule",
        [
            "",
            "FREQ=HOURLY",  # unsupported frequency
            "FREQ=WEEKLY;BYDAY=2MO",  # positional prefix, deliberately unsupported
            "FREQ=WEEKLY;INTERVAL=0",
            "FREQ=WEEKLY;INTERVAL=9999",
            "FREQ=MONTHLY;BYDAY=MO",  # BYDAY only makes sense weekly here
            "FREQ=DAILY;COUNT=0",
            "FREQ=DAILY;UNTIL=notadate",
            "nonsense",
        ],
    )
    def test_rejects_what_it_does_not_understand(self, rule: str) -> None:
        """Silence, not a guess.

        The caller's fallback is "this task does not recur" — visible and
        harmless. Guessing would put a task on a day nobody asked for.
        """
        assert parse(rule) is None

    def test_round_trips_through_to_rrule(self) -> None:
        original = "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH;COUNT=10"
        parsed = parse(original)
        assert parsed is not None
        assert parse(parsed.to_rrule()) == parsed

    def test_describes_itself_in_french(self) -> None:
        rule = parse("FREQ=WEEKLY;BYDAY=MO")
        assert rule is not None
        assert "lundis" in rule.describe()
        daily = parse("FREQ=DAILY;INTERVAL=3")
        assert daily is not None
        assert daily.describe() == "Tous les 3 jours"


class TestNextOccurrence:
    def test_anchors_on_the_due_date_not_on_completion(self) -> None:
        """A Monday task completed on Wednesday is still due next Monday.

        Anchoring on the completion time makes a weekly schedule drift a little
        every week until it means nothing.
        """
        monday = datetime(2026, 6, 8, 9, tzinfo=UTC)
        completed_wednesday = datetime(2026, 6, 10, 16, tzinfo=UTC)

        result = next_occurrence(
            "FREQ=WEEKLY;BYDAY=MO", previous_due=monday, now=completed_wednesday
        )

        assert result is not None
        assert result.date() == date(2026, 6, 15)
        assert result.hour == 9

    def test_catches_up_to_the_future_in_one_step(self) -> None:
        """Three weeks away must not produce three overdue copies."""
        long_ago = datetime(2026, 5, 4, 9, tzinfo=UTC)
        now = datetime(2026, 6, 10, 12, tzinfo=UTC)

        result = next_occurrence("FREQ=WEEKLY;BYDAY=MO", previous_due=long_ago, now=now)

        assert result is not None
        assert result.date() == date(2026, 6, 15)

    def test_an_occurrence_a_minute_away_is_still_in_the_future(self) -> None:
        due = datetime(2026, 6, 10, 9, tzinfo=UTC)
        now = datetime(2026, 6, 11, 8, 59, tzinfo=UTC)

        result = next_occurrence("FREQ=DAILY", previous_due=due, now=now)

        assert result is not None
        assert result == datetime(2026, 6, 11, 9, tzinfo=UTC)

    def test_monthly_clamps_instead_of_overflowing(self) -> None:
        """31 January + 1 month is 28 February, not 3 March.

        Overflowing is what a naive 30-day delta does, and it turns a monthly
        task into one that slowly walks through the calendar.
        """
        due = datetime(2026, 1, 31, 9, tzinfo=UTC)
        now = datetime(2026, 2, 1, tzinfo=UTC)

        result = next_occurrence("FREQ=MONTHLY", previous_due=due, now=now)

        assert result is not None
        assert result.date() == date(2026, 2, 28)

    def test_keeps_the_wall_clock_time_across_a_dst_boundary(self) -> None:
        """A 09:00 daily task stays at 09:00 in the user's zone.

        Europe/Paris moves from UTC+2 to UTC+1 on 25 October 2026, so the same
        wall time is a different UTC instant either side of it.
        """
        from zoneinfo import ZoneInfo

        paris = ZoneInfo("Europe/Paris")
        due = datetime(2026, 10, 24, 9, tzinfo=paris)
        now = datetime(2026, 10, 24, 12, tzinfo=paris)

        result = next_occurrence("FREQ=DAILY", previous_due=due, now=now, timezone="Europe/Paris")

        assert result is not None
        assert result.astimezone(paris).hour == 9
        assert result.astimezone(paris).date() == date(2026, 10, 25)

    def test_every_other_week_skips_the_intervening_one(self) -> None:
        due = datetime(2026, 6, 8, 9, tzinfo=UTC)
        now = datetime(2026, 6, 8, 10, tzinfo=UTC)

        result = next_occurrence("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO", previous_due=due, now=now)

        assert result is not None
        assert result.date() == date(2026, 6, 22)

    def test_stops_at_count(self) -> None:
        due = datetime(2026, 6, 8, 9, tzinfo=UTC)
        now = datetime(2026, 6, 8, 10, tzinfo=UTC)

        assert (
            next_occurrence("FREQ=DAILY;COUNT=3", previous_due=due, now=now, occurrences_so_far=3)
            is None
        )
        assert (
            next_occurrence("FREQ=DAILY;COUNT=3", previous_due=due, now=now, occurrences_so_far=2)
            is not None
        )

    def test_stops_after_until(self) -> None:
        due = datetime(2026, 6, 8, 9, tzinfo=UTC)
        now = datetime(2026, 6, 8, 10, tzinfo=UTC)

        assert next_occurrence("FREQ=WEEKLY;UNTIL=20260610", previous_due=due, now=now) is None

    def test_an_unsupported_rule_simply_does_not_recur(self) -> None:
        due = datetime(2026, 6, 8, 9, tzinfo=UTC)
        assert next_occurrence("FREQ=HOURLY", previous_due=due, now=due) is None
        assert next_occurrence(None, previous_due=due, now=due) is None

    def test_falls_back_to_utc_on_an_unknown_timezone(self) -> None:
        due = datetime(2026, 6, 8, 9, tzinfo=UTC)
        result = next_occurrence(
            "FREQ=DAILY", previous_due=due, now=due, timezone="Mars/Olympus_Mons"
        )
        assert result is not None
