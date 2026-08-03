"""Recurrence: from an RRULE string to the next occurrence.

`temporal.resolve` already turns "tous les lundis" into `FREQ=WEEKLY;BYDAY=MO`.
That was enough for phase 1, where a recurring task was a recurring *label*.
Phase 2 makes it a recurring *task*: completing one occurrence produces the next.

Three decisions worth stating, because each one is a bug someone will otherwise
report as a bug:

1. **The next occurrence is computed from the previous due date, not from the
   completion time.** A weekly Monday task completed on Wednesday is still due
   the following Monday, not the following Wednesday. Anchoring on completion
   makes a recurring schedule drift a little further every week until it means
   nothing.

2. **A schedule that has fallen behind catches up to the future in one step.**
   Reopening the app after three weeks away must not create three overdue
   copies of the same chore. The next occurrence is the first one strictly after
   *now*, not the one immediately after the missed date.

3. **This module deliberately implements a subset of RFC 5545.** Full RRULE
   (BYSETPOS, BYMONTHDAY with negative indices, EXDATE, WKST…) is a large
   surface for a feature whose demand is "every Monday" and "every month". The
   parser rejects what it does not understand instead of guessing — an
   unsupported rule yields no next occurrence, and the task simply stops
   recurring rather than recurring wrongly.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ISO weekday (Monday = 0) for each RRULE day token.
WEEKDAY_TOKENS: dict[str, int] = {
    "MO": 0,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "FR": 4,
    "SA": 5,
    "SU": 6,
}
TOKEN_BY_WEEKDAY = {index: token for token, index in WEEKDAY_TOKENS.items()}

SUPPORTED_FREQUENCIES = frozenset({"DAILY", "WEEKLY", "MONTHLY", "YEARLY"})

# A rule that would generate occurrences forever at a rate nobody asked for is
# more likely a parsing accident than an intention.
MAX_INTERVAL = 365

# Guard against a pathological search (a BYDAY set that never matches, say).
_MAX_STEPS = 800


@dataclass(frozen=True, slots=True)
class RecurrenceRule:
    frequency: str
    interval: int = 1
    by_weekday: tuple[int, ...] = ()
    count: int | None = None
    until: date | None = None

    def to_rrule(self) -> str:
        parts = [f"FREQ={self.frequency}"]
        if self.interval != 1:
            parts.append(f"INTERVAL={self.interval}")
        if self.by_weekday:
            parts.append("BYDAY=" + ",".join(TOKEN_BY_WEEKDAY[day] for day in self.by_weekday))
        if self.count is not None:
            parts.append(f"COUNT={self.count}")
        if self.until is not None:
            parts.append(f"UNTIL={self.until.strftime('%Y%m%d')}")
        return ";".join(parts)

    def describe(self) -> str:
        """Human wording, for the interface. French — the product's language."""
        every = "" if self.interval == 1 else f"{self.interval} "
        if self.frequency == "DAILY":
            base = "Tous les jours" if self.interval == 1 else f"Tous les {self.interval} jours"
        elif self.frequency == "WEEKLY":
            if self.by_weekday:
                names = ", ".join(_DAY_NAMES[day] for day in sorted(self.by_weekday))
                base = (
                    f"Tous les {names}"
                    if self.interval == 1
                    else f"Toutes les {every}semaines, {names}"
                )
            else:
                base = (
                    "Toutes les semaines"
                    if self.interval == 1
                    else f"Toutes les {self.interval} semaines"
                )
        elif self.frequency == "MONTHLY":
            base = "Tous les mois" if self.interval == 1 else f"Tous les {self.interval} mois"
        else:
            base = "Tous les ans" if self.interval == 1 else f"Tous les {self.interval} ans"

        if self.until is not None:
            base += f" jusqu'au {self.until.strftime('%d/%m/%Y')}"
        elif self.count is not None:
            base += f" ({self.count} fois)"
        return base


_DAY_NAMES = {
    0: "lundis",
    1: "mardis",
    2: "mercredis",
    3: "jeudis",
    4: "vendredis",
    5: "samedis",
    6: "dimanches",
}


def parse(rule: str | None) -> RecurrenceRule | None:
    """Parse an RRULE string. Returns None for anything not understood.

    Silence on an unparseable rule is deliberate: the caller's fallback is "this
    task does not recur", which is a visible, harmless outcome. Guessing would
    put a task on the user's calendar on a day they never asked for.
    """
    if not rule:
        return None

    parts: dict[str, str] = {}
    for chunk in rule.replace("RRULE:", "").split(";"):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        parts[key.strip().upper()] = value.strip().upper()

    frequency = parts.get("FREQ", "")
    if frequency not in SUPPORTED_FREQUENCIES:
        return None

    try:
        interval = int(parts.get("INTERVAL", "1"))
    except ValueError:
        return None
    if interval < 1 or interval > MAX_INTERVAL:
        return None

    by_weekday: list[int] = []
    if "BYDAY" in parts:
        for token in parts["BYDAY"].split(","):
            # Positional prefixes ("2MO" = second Monday) are not supported; a
            # rule carrying one is rejected rather than silently read as "MO".
            clean = token.strip()
            if clean not in WEEKDAY_TOKENS:
                return None
            by_weekday.append(WEEKDAY_TOKENS[clean])
    if by_weekday and frequency not in ("WEEKLY", "DAILY"):
        return None

    count: int | None = None
    if "COUNT" in parts:
        try:
            count = int(parts["COUNT"])
        except ValueError:
            return None
        if count < 1:
            return None

    until: date | None = None
    if "UNTIL" in parts:
        until = _parse_until(parts["UNTIL"])
        if until is None:
            return None

    return RecurrenceRule(
        frequency=frequency,
        interval=interval,
        by_weekday=tuple(sorted(set(by_weekday))),
        count=count,
        until=until,
    )


def _parse_until(value: str) -> date | None:
    match = re.match(r"^(\d{4})(\d{2})(\d{2})", value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def next_occurrence(
    rule: str | None,
    *,
    previous_due: datetime,
    now: datetime,
    timezone: str = "UTC",
    occurrences_so_far: int = 1,
) -> datetime | None:
    """The next due date after [previous_due], skipped forward past [now].

    Returns None when the rule is unsupported, exhausted (COUNT) or expired
    (UNTIL) — all three mean the same thing to the caller: stop recurring.

    The arithmetic is done on the *local* calendar and converted back to UTC, so
    a 09:00 daily task stays at 09:00 across a DST boundary instead of drifting
    to 08:00 for half the year.
    """
    parsed = parse(rule)
    if parsed is None:
        return None
    if parsed.count is not None and occurrences_so_far >= parsed.count:
        return None

    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")

    local_previous = previous_due.astimezone(zone)
    local_now = now.astimezone(zone)
    wall_time = local_previous.timetz().replace(tzinfo=None)

    candidate_date = local_previous.date()
    for _ in range(_MAX_STEPS):
        candidate_date = _advance(parsed, candidate_date)
        candidate = datetime.combine(candidate_date, wall_time, tzinfo=zone)
        if parsed.until is not None and candidate_date > parsed.until:
            return None
        # Strictly after now: an occurrence due in the next minute is still in
        # the future and must not be skipped.
        if candidate > local_now:
            return candidate.astimezone(previous_due.tzinfo or zone)
    return None


def _advance(rule: RecurrenceRule, current: date) -> date:
    """One step forward. Weekday sets step day by day; everything else jumps."""
    if rule.by_weekday:
        # With a BYDAY set the interval counts *weeks*, so stepping one day at a
        # time and filtering is both correct and simple. The alternative — jump
        # arithmetic per weekday — is where off-by-one bugs live.
        probe = current + timedelta(days=1)
        for _ in range(7 * max(rule.interval, 1) + 7):
            if probe.weekday() in rule.by_weekday and _week_matches(rule, current, probe):
                return probe
            probe += timedelta(days=1)
        return probe

    if rule.frequency == "DAILY":
        return current + timedelta(days=rule.interval)
    if rule.frequency == "WEEKLY":
        return current + timedelta(weeks=rule.interval)
    if rule.frequency == "MONTHLY":
        return _add_months(current, rule.interval)
    return _add_months(current, 12 * rule.interval)


def _week_matches(rule: RecurrenceRule, anchor: date, probe: date) -> bool:
    if rule.interval == 1:
        return True
    anchor_week = _monday_of(anchor)
    probe_week = _monday_of(probe)
    return ((probe_week - anchor_week).days // 7) % rule.interval == 0


def _monday_of(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _add_months(value: date, months: int) -> date:
    """Month arithmetic that clamps rather than overflows.

    31 January + 1 month is 28 February (or the 29th), not 3 March. Overflowing
    is what naive `timedelta(days=30)` does, and it turns a monthly task into a
    task that slowly walks through the calendar.
    """
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
