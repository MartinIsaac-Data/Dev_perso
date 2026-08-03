"""Search query language.

A single text box that accepts both free text and filters:

    réunion DAF is:task p:high #finance @refonte due:semaine

The parser is here, in the domain, rather than in the API layer, because it is a
*language* — it has semantics, it needs tests, and the same grammar is used by
full-text search, by the command palette and by saved filters. Parsing it three
times in three places is how three subtly different behaviours appear.

Design rules:

* **An unrecognised token is free text, never an error.** Somebody typing
  "budget: 3000" is searching for a budget, not writing a malformed filter. A
  search box that rejects input is a search box people stop using.
* **Unknown filter *values* are dropped, not guessed.** `p:hgih` filters on
  nothing rather than on `high`; the caller can see it in `ignored`.
* **Repeating a filter widens, it does not replace.** `is:task is:idea` means
  either, because that is what the same syntax means in every tool the user has
  already learned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.enums import EntryStatus, EntryType, Priority

# Quoted phrases survive tokenisation as a single term.
_TOKEN = re.compile(r'"[^"]*"|\S+')

_TYPE_ALIASES: dict[str, EntryType] = {
    "task": EntryType.TASK,
    "tache": EntryType.TASK,
    "tâche": EntryType.TASK,
    "todo": EntryType.TASK,
    "idea": EntryType.IDEA,
    "idee": EntryType.IDEA,
    "idée": EntryType.IDEA,
    "note": EntryType.NOTE,
    "decision": EntryType.DECISION,
    "décision": EntryType.DECISION,
    "question": EntryType.QUESTION,
    "meeting": EntryType.MEETING,
    "reunion": EntryType.MEETING,
    "réunion": EntryType.MEETING,
    "reminder": EntryType.REMINDER,
    "rappel": EntryType.REMINDER,
}

_STATUS_ALIASES: dict[str, EntryStatus] = {
    "done": EntryStatus.DONE,
    "fait": EntryStatus.DONE,
    "termine": EntryStatus.DONE,
    "terminé": EntryStatus.DONE,
    "active": EntryStatus.ACTIVE,
    "actif": EntryStatus.ACTIVE,
    "open": EntryStatus.ACTIVE,
    "ouvert": EntryStatus.ACTIVE,
    "archived": EntryStatus.ARCHIVED,
    "archive": EntryStatus.ARCHIVED,
    "archivé": EntryStatus.ARCHIVED,
    "snoozed": EntryStatus.SNOOZED,
    "reporte": EntryStatus.SNOOZED,
    "reporté": EntryStatus.SNOOZED,
    "review": EntryStatus.NEEDS_REVIEW,
    "needs_review": EntryStatus.NEEDS_REVIEW,
    "verifier": EntryStatus.NEEDS_REVIEW,
    "vérifier": EntryStatus.NEEDS_REVIEW,
}

_PRIORITY_ALIASES: dict[str, Priority] = {
    "low": Priority.LOW,
    "basse": Priority.LOW,
    "normal": Priority.NORMAL,
    "normale": Priority.NORMAL,
    "high": Priority.HIGH,
    "haute": Priority.HIGH,
    "important": Priority.HIGH,
    "urgent": Priority.URGENT,
    "urgente": Priority.URGENT,
}

# `is:` accepts both a type and a status, because users do not hold the
# distinction in their heads and both readings are unambiguous here.
_FLAGS = frozenset({"overdue", "today", "week", "flagged", "starred", "pinned", "recurring"})


@dataclass(slots=True)
class DateRange:
    start: datetime | None = None
    end: datetime | None = None

    @property
    def bounded(self) -> bool:
        return self.start is not None or self.end is not None


@dataclass(slots=True)
class ParsedQuery:
    """The structured half of a query. `text` is what is left for full-text."""

    text: str = ""
    types: list[EntryType] = field(default_factory=list)
    statuses: list[EntryStatus] = field(default_factory=list)
    priorities: list[Priority] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    due: DateRange | None = None
    created: DateRange | None = None
    overdue: bool = False
    recurring: bool = False
    pinned: bool = False
    # Tokens that looked like filters but named nothing we know. Surfaced so the
    # interface can say "p:hgih ignoré" instead of silently returning everything.
    ignored: list[str] = field(default_factory=list)

    @property
    def has_filters(self) -> bool:
        return bool(
            self.types
            or self.statuses
            or self.priorities
            or self.tags
            or self.projects
            or (self.due and self.due.bounded)
            or (self.created and self.created.bounded)
            or self.overdue
            or self.recurring
            or self.pinned
        )

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.has_filters


def parse_query(
    raw: str, *, now: datetime | None = None, timezone: str = "Europe/Paris"
) -> ParsedQuery:
    reference = now or datetime.now(_zone(timezone))
    parsed = ParsedQuery()
    free_terms: list[str] = []

    for match in _TOKEN.finditer(raw or ""):
        token = match.group(0)
        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            phrase = token[1:-1].strip()
            if phrase:
                free_terms.append(phrase)
            continue

        if _apply_prefix(parsed, token) or _apply_filter(parsed, token, reference, timezone):
            continue
        free_terms.append(token)

    parsed.text = " ".join(free_terms).strip()
    return parsed


def _apply_prefix(parsed: ParsedQuery, token: str) -> bool:
    """`#tag` and `@project` — the shorthand people type without thinking."""
    if len(token) > 1 and token[0] == "#":
        parsed.tags.append(_normalise_tag(token[1:]))
        return True
    if len(token) > 1 and token[0] == "@":
        parsed.projects.append(token[1:].strip().lower())
        return True
    return False


def _apply_filter(parsed: ParsedQuery, token: str, now: datetime, timezone: str) -> bool:
    if ":" not in token:
        return False
    key, _, value = token.partition(":")
    key = key.strip().lower()
    value = value.strip().lower()
    if not value:
        return False

    if key in ("is", "type", "status", "statut"):
        return _apply_is(parsed, token, key, value)
    if key in ("p", "priority", "priorite", "priorité"):
        priority = _PRIORITY_ALIASES.get(value)
        if priority is None:
            parsed.ignored.append(token)
        else:
            parsed.priorities.append(priority)
        return True
    if key in ("tag", "label"):
        parsed.tags.append(_normalise_tag(value))
        return True
    if key in ("project", "projet", "proj"):
        parsed.projects.append(value)
        return True
    if key in ("due", "echeance", "échéance"):
        window = _date_window(value, now, timezone)
        if window is None:
            parsed.ignored.append(token)
        else:
            parsed.due = window
        return True
    if key in ("created", "cree", "créé"):
        window = _date_window(value, now, timezone)
        if window is None:
            parsed.ignored.append(token)
        else:
            parsed.created = window
        return True
    return False


def _apply_is(parsed: ParsedQuery, token: str, key: str, value: str) -> bool:
    if key in ("status", "statut"):
        status = _STATUS_ALIASES.get(value)
        if status is None:
            parsed.ignored.append(token)
        else:
            parsed.statuses.append(status)
        return True
    if key == "type":
        entry_type = _TYPE_ALIASES.get(value)
        if entry_type is None:
            parsed.ignored.append(token)
        else:
            parsed.types.append(entry_type)
        return True

    # Bare `is:` — try type, then status, then the flags.
    entry_type = _TYPE_ALIASES.get(value)
    if entry_type is not None:
        parsed.types.append(entry_type)
        return True
    status = _STATUS_ALIASES.get(value)
    if status is not None:
        parsed.statuses.append(status)
        return True
    if value in _FLAGS:
        if value == "overdue":
            parsed.overdue = True
        elif value == "recurring":
            parsed.recurring = True
        elif value in ("pinned", "flagged", "starred"):
            parsed.pinned = True
        return True
    parsed.ignored.append(token)
    return True


def _date_window(value: str, now: datetime, timezone: str) -> DateRange | None:
    """Windows, not instants.

    `due:today` must include everything due today, not everything due at this
    exact second. Every keyword here resolves to a half-open [start, end) range
    over the *user's* local calendar.
    """
    zone = _zone(timezone)
    local = now.astimezone(zone)
    today = local.date()

    def span(start: date, end: date) -> DateRange:
        return DateRange(
            start=datetime.combine(start, time.min, tzinfo=zone),
            end=datetime.combine(end, time.min, tzinfo=zone),
        )

    if value in ("today", "aujourdhui", "aujourd'hui"):
        return span(today, today + timedelta(days=1))
    if value in ("tomorrow", "demain"):
        return span(today + timedelta(days=1), today + timedelta(days=2))
    if value in ("yesterday", "hier"):
        return span(today - timedelta(days=1), today)
    if value in ("week", "semaine", "this_week"):
        monday = today - timedelta(days=today.weekday())
        return span(monday, monday + timedelta(days=7))
    if value in ("next_week", "prochaine_semaine"):
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return span(monday, monday + timedelta(days=7))
    if value in ("month", "mois"):
        first = today.replace(day=1)
        following = (first + timedelta(days=32)).replace(day=1)
        return span(first, following)
    if value in ("overdue", "retard"):
        return DateRange(end=local)
    if value in ("none", "aucune", "sans"):
        # An explicitly unbounded window: "no due date". Distinguished from a
        # missing filter by being present-but-empty.
        return DateRange()

    explicit = _explicit_date(value)
    if explicit is not None:
        return span(explicit, explicit + timedelta(days=1))
    return None


def _explicit_date(value: str) -> date | None:
    for pattern, order in (
        (r"^(\d{4})-(\d{2})-(\d{2})$", (1, 2, 3)),
        (r"^(\d{2})/(\d{2})/(\d{4})$", (3, 2, 1)),
    ):
        match = re.match(pattern, value)
        if match:
            try:
                return date(
                    int(match.group(order[0])),
                    int(match.group(order[1])),
                    int(match.group(order[2])),
                )
            except ValueError:
                return None
    return None


def _normalise_tag(value: str) -> str:
    return value.strip().lstrip("#").lower()


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def to_websearch(text: str) -> str:
    """Prepare free text for PostgreSQL `websearch_to_tsquery`.

    That function already understands quotes, `or` and `-exclusion`, and — the
    reason it is chosen over `to_tsquery` — it never raises on malformed input.
    A search box must not be able to return a 500.
    """
    return " ".join(text.split())[:200]
