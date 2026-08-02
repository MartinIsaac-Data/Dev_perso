"""Deterministic temporal resolution (ADR-020, AI.md §5.1).

The LLM spots the expression; this module resolves it. Rationale: a model produces
a *plausible and wrong* date with no signal of uncertainty, and a wrong due date
destroys trust faster than any other error in the product.

Two safety rules govern everything here:

1. An expression this module cannot resolve with confidence yields **no date at
   all**. The raw wording is kept on the entry instead. No date beats a wrong one.
2. A date resolved more than 24 h in the past is rejected — it signals a
   misreading, not a user who wants a deadline in the past.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.enums import DuePrecision

# Conventions, documented so they can be argued with rather than guessed at.
DEFAULT_DAY_HOUR = 9  # a day-precision deadline lands at 09:00 local
EVENING_HOUR = 19
MORNING_HOUR = 9
NOON_HOUR = 12
AFTERNOON_HOUR = 14
END_OF_WEEK_WEEKDAY = 4  # Friday
END_OF_WEEK_HOUR = 18
PAST_TOLERANCE = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class ResolvedDate:
    expression: str
    due_at: datetime | None = None
    precision: DuePrecision | None = None
    recurrence_rule: str | None = None
    unresolved_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.due_at is not None or self.recurrence_rule is not None


_WEEKDAYS: dict[str, int] = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_MONTHS: dict[str, int] = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_NUMBERS: dict[str, int] = {
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "quinze": 15,
    "vingt": 20,
    "trente": 30,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six_en": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
}

# Expressions that carry no actionable deadline. Matching one of these is a
# *successful* outcome: it means "deliberately no date".
_FUZZY = (
    "bientot",
    "un de ces jours",
    "plus tard",
    "prochainement",
    "des que possible",
    "quand j aurai le temps",
    "un jour",
    "someday",
    "soon",
    "later",
    "eventually",
    "asap",
    "when i can",
)


def _strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn"
    )


def _normalize(value: str) -> str:
    text = _strip_accents(value.lower().strip())
    text = re.sub(r"[\u2019']", " ", text)
    # A hyphen between two letters is a word separator ("après-demain"); between
    # digits it is a date separator ("12-06-2026") and must survive.
    text = re.sub(r"(?<=[a-z])[-\u2013\u2014](?=[a-z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _at(local_date: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    """Build an aware datetime, then convert to UTC.

    Going through the zone (rather than doing arithmetic in UTC) is what makes
    DST transitions correct: 09:00 local is 09:00 local on both sides of the
    change, even though the UTC offset differs.
    """
    return datetime.combine(local_date, time(hour, minute), tzinfo=tz).astimezone(ZoneInfo("UTC"))


def _number(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return _NUMBERS.get(token)


def resolve(
    expression: str,
    *,
    captured_at: datetime,
    timezone: str = "Europe/Paris",
) -> ResolvedDate:
    """Resolve a raw temporal expression against the moment of capture."""
    if not expression or not expression.strip():
        return ResolvedDate(expression=expression, unresolved_reason="empty")

    tz = _zone(timezone)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=ZoneInfo("UTC"))
    local_now = captured_at.astimezone(tz)
    today = local_now.date()
    text = _normalize(expression)

    for resolver in (
        _resolve_fuzzy,
        _resolve_recurrence,
        _resolve_explicit_date,
        _resolve_numeric_date,
        _resolve_relative_day,
        _resolve_offset,
        _resolve_period_bound,
        _resolve_weekday,
        _resolve_time_only,
    ):
        result = resolver(text, expression, today, local_now, tz)
        if result is not None:
            return _guard_past(result, captured_at)

    return ResolvedDate(expression=expression, unresolved_reason="unrecognised")


def _guard_past(result: ResolvedDate, captured_at: datetime) -> ResolvedDate:
    if result.due_at is not None and result.due_at < captured_at - PAST_TOLERANCE:
        return ResolvedDate(expression=result.expression, unresolved_reason="resolved_in_past")
    return result


# --------------------------------------------------------------------------- #
# Resolvers, tried in order of specificity
# --------------------------------------------------------------------------- #
def _resolve_fuzzy(
    text: str, raw: str, _today: date, _now: datetime, _tz: ZoneInfo
) -> ResolvedDate | None:
    if any(marker in text for marker in _FUZZY):
        return ResolvedDate(expression=raw, unresolved_reason="deliberately_vague")
    return None


def _resolve_recurrence(
    text: str, raw: str, _today: date, _now: datetime, _tz: ZoneInfo
) -> ResolvedDate | None:
    match = re.search(r"\b(?:tous les|toutes les|chaque|every)\s+(\w+)", text)
    if not match:
        return None
    token = match.group(1).rstrip("s")
    if token in _WEEKDAYS:
        byday = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][_WEEKDAYS[token]]
        return ResolvedDate(expression=raw, recurrence_rule=f"FREQ=WEEKLY;BYDAY={byday}")
    if token in ("jour", "day"):
        return ResolvedDate(expression=raw, recurrence_rule="FREQ=DAILY")
    if token in ("semaine", "week"):
        return ResolvedDate(expression=raw, recurrence_rule="FREQ=WEEKLY")
    if token in ("mois", "month"):
        return ResolvedDate(expression=raw, recurrence_rule="FREQ=MONTHLY")
    return ResolvedDate(expression=raw, unresolved_reason="unsupported_recurrence")


def _resolve_explicit_date(
    text: str, raw: str, today: date, _now: datetime, tz: ZoneInfo
) -> ResolvedDate | None:
    """'12 juin', 'le 12 juin 2026', 'June 12'."""
    match = re.search(r"\b(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?", text)
    if match and match.group(2) in _MONTHS:
        day, month, year = int(match.group(1)), _MONTHS[match.group(2)], match.group(3)
        return _build_calendar_date(day, month, year, raw, today, tz, text)

    match = re.search(r"\b([a-z]+)\s+(\d{1,2})(?:\D|$)", text)
    if match and match.group(1) in _MONTHS:
        day, month = int(match.group(2)), _MONTHS[match.group(1)]
        return _build_calendar_date(day, month, None, raw, today, tz, text)
    return None


def _resolve_numeric_date(
    text: str, raw: str, today: date, _now: datetime, tz: ZoneInfo
) -> ResolvedDate | None:
    """'12/06', '12/06/2026' — day first, per FR convention."""
    match = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", text)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    year = match.group(3)
    if year and len(year) == 2:
        year = f"20{year}"
    return _build_calendar_date(day, month, year, raw, today, tz, text)


def _build_calendar_date(
    day: int,
    month: int,
    year: str | None,
    raw: str,
    today: date,
    tz: ZoneInfo,
    text: str,
) -> ResolvedDate | None:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        if year:
            target = date(int(year), month, day)
        else:
            target = date(today.year, month, day)
            if target < today:  # no year given: assume the next occurrence
                target = date(today.year + 1, month, day)
    except ValueError:
        return ResolvedDate(expression=raw, unresolved_reason="invalid_calendar_date")

    hour, minute, precision = _extract_time(text)
    return ResolvedDate(
        expression=raw,
        due_at=_at(target, hour, minute, tz),
        precision=precision,
    )


def _resolve_relative_day(
    text: str, raw: str, today: date, _now: datetime, tz: ZoneInfo
) -> ResolvedDate | None:
    offsets = {
        "apres demain": 2,
        "day after tomorrow": 2,
        "avant hier": -2,
        "day before yesterday": -2,
        "demain": 1,
        "tomorrow": 1,
        "aujourd hui": 0,
        "today": 0,
        "ce soir": 0,
        "tonight": 0,
        "hier": -1,
        "yesterday": -1,
    }
    for marker, offset in offsets.items():
        if marker in text:
            hour, minute, precision = _extract_time(text)
            if marker in ("ce soir", "tonight") and precision is DuePrecision.DAY:
                hour, precision = EVENING_HOUR, DuePrecision.HOUR
            return ResolvedDate(
                expression=raw,
                due_at=_at(today + timedelta(days=offset), hour, minute, tz),
                precision=precision,
            )
    return None


def _resolve_offset(
    text: str, raw: str, today: date, _now: datetime, tz: ZoneInfo
) -> ResolvedDate | None:
    """'dans deux semaines', 'd'ici 3 jours', 'in 2 weeks'."""
    match = re.search(
        r"\b(?:dans|d ici|sous|in|within)\s+(\w+)\s+(jour|jours|semaine|semaines|"
        r"mois|day|days|week|weeks|month|months)\b",
        text,
    )
    if not match:
        return None
    amount = _number(match.group(1))
    if amount is None:
        return ResolvedDate(expression=raw, unresolved_reason="unparsed_quantity")

    unit = match.group(2)
    if unit.startswith(("jour", "day")):
        target = today + timedelta(days=amount)
    elif unit.startswith(("semaine", "week")):
        target = today + timedelta(weeks=amount)
    else:
        month_index = today.month - 1 + amount
        year = today.year + month_index // 12
        month = month_index % 12 + 1
        day = min(today.day, _days_in_month(year, month))
        target = date(year, month, day)

    hour, minute, precision = _extract_time(text)
    return ResolvedDate(expression=raw, due_at=_at(target, hour, minute, tz), precision=precision)


def _resolve_period_bound(
    text: str, raw: str, today: date, _now: datetime, tz: ZoneInfo
) -> ResolvedDate | None:
    if re.search(r"\b(fin de (la )?semaine|end of (the )?week)\b", text):
        delta = (END_OF_WEEK_WEEKDAY - today.weekday()) % 7
        return ResolvedDate(
            expression=raw,
            due_at=_at(today + timedelta(days=delta), END_OF_WEEK_HOUR, 0, tz),
            precision=DuePrecision.HOUR,
        )
    if re.search(r"\b(fin de (ce )?mois|fin du mois|end of (the )?month)\b", text):
        last = _days_in_month(today.year, today.month)
        return ResolvedDate(
            expression=raw,
            due_at=_at(date(today.year, today.month, last), END_OF_WEEK_HOUR, 0, tz),
            precision=DuePrecision.HOUR,
        )
    if re.search(r"\b(debut de (la )?semaine prochaine|next week)\b", text):
        delta = (7 - today.weekday()) % 7 or 7
        return ResolvedDate(
            expression=raw,
            due_at=_at(today + timedelta(days=delta), DEFAULT_DAY_HOUR, 0, tz),
            precision=DuePrecision.DAY,
        )
    if re.search(r"\b(debut (de l )?annee prochaine|next year)\b", text):
        return ResolvedDate(
            expression=raw,
            due_at=_at(date(today.year + 1, 1, 5), DEFAULT_DAY_HOUR, 0, tz),
            precision=DuePrecision.DAY,
        )
    return None


def _resolve_weekday(
    text: str, raw: str, today: date, _now: datetime, tz: ZoneInfo
) -> ResolvedDate | None:
    for name, index in _WEEKDAYS.items():
        if not re.search(rf"\b{name}\b", text):
            continue
        # Strict next occurrence: "jeudi" said on a Thursday means next Thursday.
        days_ahead = (index - today.weekday()) % 7 or 7
        target = today + timedelta(days=days_ahead)
        # "prochain" pushes a week further when the plain answer is still in the
        # current calendar week (AI.md §5.1).
        if re.search(r"\b(prochain|prochaine|next)\b", text) and (
            target.isocalendar()[:2] == today.isocalendar()[:2]
        ):
            target += timedelta(days=7)
        hour, minute, precision = _extract_time(text)
        return ResolvedDate(
            expression=raw, due_at=_at(target, hour, minute, tz), precision=precision
        )
    return None


def _resolve_time_only(
    text: str, raw: str, today: date, now: datetime, tz: ZoneInfo
) -> ResolvedDate | None:
    hour, minute, precision = _extract_time(text)
    if precision is DuePrecision.DAY:
        return None
    target = today
    candidate = _at(target, hour, minute, tz)
    if candidate <= now.astimezone(ZoneInfo("UTC")):
        candidate = _at(target + timedelta(days=1), hour, minute, tz)
    return ResolvedDate(expression=raw, due_at=candidate, precision=precision)


def _extract_time(text: str) -> tuple[int, int, DuePrecision]:
    """Return (hour, minute, precision) for the time-of-day part, if any."""
    match = re.search(r"\b(\d{1,2})\s*[h:]\s*(\d{2})\b", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute, DuePrecision.MINUTE

    match = re.search(r"\b(\d{1,2})\s*h\b", text)
    if match and 0 <= int(match.group(1)) <= 23:
        return int(match.group(1)), 0, DuePrecision.HOUR

    match = re.search(r"\b(?:a|at)\s+(\d{1,2})\s*(am|pm)?\b", text)
    if match:
        hour = int(match.group(1))
        if match.group(2) == "pm" and hour < 12:
            hour += 12
        elif match.group(2) == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23:
            return hour, 0, DuePrecision.HOUR

    for marker, hour in (
        ("ce soir", EVENING_HOUR),
        ("tonight", EVENING_HOUR),
        ("soir", EVENING_HOUR),
        ("matin", MORNING_HOUR),
        ("morning", MORNING_HOUR),
        ("midi", NOON_HOUR),
        ("noon", NOON_HOUR),
        ("apres midi", AFTERNOON_HOUR),
        ("afternoon", AFTERNOON_HOUR),
    ):
        if marker in text:
            return hour, 0, DuePrecision.HOUR

    return DEFAULT_DAY_HOUR, 0, DuePrecision.DAY


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day
