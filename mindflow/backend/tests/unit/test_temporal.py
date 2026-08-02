"""Temporal resolution tests (Sprint02 epic 14.3).

DST cases are here deliberately: the spring-forward bug is silent, seasonal, and
impossible to reproduce six months later.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.enums import DuePrecision
from app.domain.temporal import resolve

UTC = ZoneInfo("UTC")
PARIS = "Europe/Paris"

# Tuesday 9 June 2026, 11:47 Paris (09:47 UTC, CEST = UTC+2)
TUESDAY = datetime(2026, 6, 9, 9, 47, tzinfo=UTC)


def r(expression: str, *, at: datetime = TUESDAY, tz: str = PARIS):
    return resolve(expression, captured_at=at, timezone=tz)


def local(result, tz: str = PARIS) -> datetime:
    assert result.due_at is not None
    return result.due_at.astimezone(ZoneInfo(tz))


# --------------------------------------------------------------------------- #
# Relative days
# --------------------------------------------------------------------------- #
def test_tomorrow() -> None:
    result = r("demain")
    assert local(result).date().isoformat() == "2026-06-10"
    assert local(result).hour == 9
    assert result.precision is DuePrecision.DAY


def test_day_after_tomorrow_is_not_matched_as_tomorrow() -> None:
    assert local(r("après-demain")).date().isoformat() == "2026-06-11"


def test_english_tomorrow() -> None:
    assert local(r("tomorrow")).date().isoformat() == "2026-06-10"


def test_tonight_lands_at_the_evening_convention() -> None:
    result = r("ce soir")
    assert local(result).date().isoformat() == "2026-06-09"
    assert local(result).hour == 19
    assert result.precision is DuePrecision.HOUR


# --------------------------------------------------------------------------- #
# Weekdays — the strict next-occurrence rule
# --------------------------------------------------------------------------- #
def test_weekday_resolves_to_the_next_occurrence() -> None:
    assert local(r("jeudi")).date().isoformat() == "2026-06-11"


def test_same_weekday_means_next_week_not_today() -> None:
    """Said on a Tuesday, 'mardi' is next Tuesday — strict next occurrence."""
    assert local(r("mardi")).date().isoformat() == "2026-06-16"


def test_prochain_pushes_a_week_when_the_day_is_still_ahead_this_week() -> None:
    """Tuesday 9th: plain 'jeudi' is the 11th (same week), so 'jeudi prochain'
    is the 18th."""
    assert local(r("jeudi prochain")).date().isoformat() == "2026-06-18"


def test_prochain_does_not_double_shift_across_the_week_boundary() -> None:
    """'lundi' from a Tuesday already lands next week; 'lundi prochain' stays there."""
    assert local(r("lundi")).date().isoformat() == "2026-06-15"
    assert local(r("lundi prochain")).date().isoformat() == "2026-06-15"


def test_weekday_with_an_hour() -> None:
    result = r("jeudi à 14h")
    assert local(result).date().isoformat() == "2026-06-11"
    assert local(result).hour == 14
    assert result.precision is DuePrecision.HOUR


# --------------------------------------------------------------------------- #
# Offsets
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("dans deux semaines", "2026-06-23"),
        ("dans 3 jours", "2026-06-12"),
        ("d'ici une semaine", "2026-06-16"),
        ("in 2 weeks", "2026-06-23"),
        ("dans un mois", "2026-07-09"),
    ],
)
def test_offsets(expression: str, expected: str) -> None:
    assert local(r(expression)).date().isoformat() == expected


def test_month_offset_clamps_to_the_last_valid_day() -> None:
    # 31 January + 1 month has no 31 February.
    january = datetime(2026, 1, 31, 10, 0, tzinfo=UTC)
    assert local(r("dans un mois", at=january)).date().isoformat() == "2026-02-28"


# --------------------------------------------------------------------------- #
# Calendar dates
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("le 12 juin", "2026-06-12"),
        ("12 juin 2027", "2027-06-12"),
        ("12/06", "2026-06-12"),
        ("12.06.2026", "2026-06-12"),
        ("June 12", "2026-06-12"),
    ],
)
def test_calendar_dates(expression: str, expected: str) -> None:
    assert local(r(expression)).date().isoformat() == expected


def test_a_date_already_past_this_year_rolls_to_next_year() -> None:
    assert local(r("le 3 février")).date().isoformat() == "2027-02-03"


def test_impossible_calendar_date_is_refused_rather_than_guessed() -> None:
    result = r("le 31 février")
    assert not result.resolved
    assert result.unresolved_reason in ("invalid_calendar_date", "unrecognised")


# --------------------------------------------------------------------------- #
# Period bounds
# --------------------------------------------------------------------------- #
def test_end_of_week_is_friday_evening() -> None:
    result = r("fin de semaine")
    assert local(result).date().isoformat() == "2026-06-12"
    assert local(result).hour == 18


def test_end_of_month() -> None:
    assert local(r("fin de mois")).date().isoformat() == "2026-06-30"


# --------------------------------------------------------------------------- #
# Fuzzy and recurrence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("expression", ["bientôt", "un de ces jours", "someday", "plus tard"])
def test_vague_expressions_produce_no_date_on_purpose(expression: str) -> None:
    result = r(expression)
    assert result.due_at is None
    assert result.unresolved_reason == "deliberately_vague"


def test_unrecognised_expression_produces_no_date() -> None:
    result = r("quelque part entre deux réunions")
    assert not result.resolved
    assert result.unresolved_reason == "unrecognised"


@pytest.mark.parametrize(
    ("expression", "rule"),
    [
        ("tous les lundis", "FREQ=WEEKLY;BYDAY=MO"),
        ("chaque jour", "FREQ=DAILY"),
        ("every month", "FREQ=MONTHLY"),
    ],
)
def test_recurrence_rules(expression: str, rule: str) -> None:
    result = r(expression)
    assert result.recurrence_rule == rule
    assert result.due_at is None


# --------------------------------------------------------------------------- #
# Safety rails
# --------------------------------------------------------------------------- #
def test_a_date_far_in_the_past_is_rejected() -> None:
    result = r("hier")
    # 'hier' at 09:00 local is ~26 h before capture: beyond the 24 h tolerance.
    assert result.due_at is None
    assert result.unresolved_reason == "resolved_in_past"


def test_empty_expression() -> None:
    assert resolve("", captured_at=TUESDAY, timezone=PARIS).unresolved_reason == "empty"


def test_unknown_timezone_falls_back_to_utc_instead_of_raising() -> None:
    result = resolve("demain", captured_at=TUESDAY, timezone="Mars/Olympus")
    assert result.due_at is not None


# --------------------------------------------------------------------------- #
# Daylight saving time
# --------------------------------------------------------------------------- #
def test_spring_forward_keeps_the_local_wall_clock() -> None:
    """Paris switches to CEST on 29 March 2026. A deadline one week after the
    25th must still be 09:00 *local*, i.e. 07:00 UTC instead of 08:00."""
    before = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    result = resolve("dans une semaine", captured_at=before, timezone=PARIS)
    assert result.due_at is not None
    assert result.due_at.isoformat() == "2026-04-01T07:00:00+00:00"
    assert local(result).hour == 9


def test_crossing_into_dst_the_next_day() -> None:
    saturday = datetime(2026, 3, 28, 12, 0, tzinfo=UTC)
    result = resolve("demain", captured_at=saturday, timezone=PARIS)
    assert result.due_at is not None
    assert result.due_at.isoformat() == "2026-03-29T07:00:00+00:00"


def test_fall_back_keeps_the_local_wall_clock() -> None:
    """Paris returns to CET on 25 October 2026."""
    before = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    result = resolve("dans une semaine", captured_at=before, timezone=PARIS)
    assert result.due_at is not None
    assert result.due_at.isoformat() == "2026-10-28T08:00:00+00:00"


def test_a_non_integer_offset_timezone_is_handled() -> None:
    result = resolve("demain", captured_at=TUESDAY, timezone="Asia/Kolkata")
    assert result.due_at is not None
    assert result.due_at.astimezone(ZoneInfo("Asia/Kolkata")).hour == 9


def test_leap_year() -> None:
    feb = datetime(2028, 2, 28, 10, 0, tzinfo=UTC)
    assert local(r("demain", at=feb)).date().isoformat() == "2028-02-29"
