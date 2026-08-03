"""Reminder offset rules.

`-15m` and `-1d@18:00` are the vocabulary the automatic scheduler speaks. Both
forms exist because they mean genuinely different things: one is relative to the
deadline's own time, the other pins a wall-clock hour on the offset day, which is
what "the day before at six" means to a person.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.enums import ReminderChannel
from app.services.reminder_service import _dedupe_key, resolve_offset

DUE = datetime(2026, 6, 12, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("-15m", datetime(2026, 6, 12, 13, 45, tzinfo=UTC)),
        ("-2h", datetime(2026, 6, 12, 12, 0, tzinfo=UTC)),
        ("-1d", datetime(2026, 6, 11, 14, 0, tzinfo=UTC)),
        ("-1w", datetime(2026, 6, 5, 14, 0, tzinfo=UTC)),
    ],
)
def test_a_bare_offset_keeps_the_deadline_time(rule: str, expected: datetime) -> None:
    assert resolve_offset(rule, due_at=DUE) == expected


def test_an_at_suffix_pins_a_wall_clock_hour() -> None:
    """ "La veille à 18h" is a time of day, not a duration."""
    assert resolve_offset("-1d@18:00", due_at=DUE) == datetime(2026, 6, 11, 18, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "rule",
    ["15m", "+15m", "-15", "-15x", "", "-1d@25:00", "-1d@12:99", "nonsense"],
)
def test_an_unparseable_rule_yields_no_instant(rule: str) -> None:
    """None rather than a guessed moment: a reminder at a time nobody asked for
    is worse than no reminder."""
    assert resolve_offset(rule, due_at=DUE) is None


class TestDedupeKey:
    def test_is_stable_for_the_same_reminder(self) -> None:
        """This is what makes the automatic scheduler idempotent: re-running it
        after an update must not stack three copies of "15 minutes before"."""
        first = _dedupe_key(None, DUE, "-15m", ReminderChannel.PUSH)
        second = _dedupe_key(None, DUE, "-15m", ReminderChannel.PUSH)
        assert first == second

    def test_changes_when_the_instant_moves(self) -> None:
        """Moving a deadline must produce a genuinely new reminder rather than
        resurrect the old one at the wrong time."""
        moved = DUE.replace(hour=16)
        assert _dedupe_key(None, DUE, "-15m", ReminderChannel.PUSH) != _dedupe_key(
            None, moved, "-15m", ReminderChannel.PUSH
        )

    def test_distinguishes_two_offsets_landing_together(self) -> None:
        assert _dedupe_key(None, DUE, "-15m", ReminderChannel.PUSH) != _dedupe_key(
            None, DUE, "-1d@18:00", ReminderChannel.PUSH
        )

    def test_distinguishes_channels(self) -> None:
        assert _dedupe_key(None, DUE, "-15m", ReminderChannel.PUSH) != _dedupe_key(
            None, DUE, "-15m", ReminderChannel.LOCAL
        )

    def test_fits_the_column(self) -> None:
        import uuid

        key = _dedupe_key(uuid.uuid4(), DUE, "-1d@18:00", ReminderChannel.PUSH)
        assert len(key) <= 120
