"""Synchronising with the outside world.

Seven destinations — Google Calendar, Outlook, Microsoft To Do, Slack, Teams,
Notion, Obsidian — and one hard problem underneath all of them: **two systems
that both accept writes will disagree, and something has to decide.**

Everything here exists to make that decision explicit rather than accidental.

**Idempotency is not optional, it is the feature.** Every external object we have
ever seen is recorded in `external_link` with its provider id. A pull that runs
twice must not create the event twice; a push that retries after a timeout must
not put a second copy in somebody's calendar. Everyone has been on the receiving
end of an integration that got this wrong.

**Conflicts are classified, and only the safe class is resolved automatically.**
Last-write-wins is what most integrations do, and it silently discards work. Here
a genuine two-sided edit is *flagged* and shown to the user. Losing an edit
quietly is worse than asking.

**Direction is a per-connection setting, defaulting to pull.** Two-way sync is
the setting most likely to surprise somebody by writing into their calendar, so
it is never the default and never inferred.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Provider(StrEnum):
    """The seven, and what each one actually is."""

    GOOGLE_CALENDAR = "google_calendar"
    OUTLOOK_CALENDAR = "outlook_calendar"
    MICROSOFT_TODO = "microsoft_todo"
    SLACK = "slack"
    TEAMS = "teams"
    NOTION = "notion"
    # Not a service: a folder of Markdown files, synced by the client, not the
    # server. Listed here because it is a destination the user chooses in the
    # same screen, and hiding that difference would be dishonest — see
    # `is_server_side`.
    OBSIDIAN = "obsidian"

    @property
    def label(self) -> str:
        return {
            Provider.GOOGLE_CALENDAR: "Google Calendar",
            Provider.OUTLOOK_CALENDAR: "Outlook Calendar",
            Provider.MICROSOFT_TODO: "Microsoft To Do",
            Provider.SLACK: "Slack",
            Provider.TEAMS: "Microsoft Teams",
            Provider.NOTION: "Notion",
            Provider.OBSIDIAN: "Obsidian",
        }[self]

    @property
    def is_server_side(self) -> bool:
        """Whether the server can sync this without the client running.

        Obsidian is a local vault. The server has no access to it and must not
        pretend otherwise: its "connection" is a client-side export contract,
        and a scheduled server job for it would never fire.
        """
        return self is not Provider.OBSIDIAN

    @property
    def kind(self) -> ConnectorKind:
        return {
            Provider.GOOGLE_CALENDAR: ConnectorKind.CALENDAR,
            Provider.OUTLOOK_CALENDAR: ConnectorKind.CALENDAR,
            Provider.MICROSOFT_TODO: ConnectorKind.TASKS,
            Provider.SLACK: ConnectorKind.MESSAGING,
            Provider.TEAMS: ConnectorKind.MESSAGING,
            Provider.NOTION: ConnectorKind.DOCUMENTS,
            Provider.OBSIDIAN: ConnectorKind.DOCUMENTS,
        }[self]

    @property
    def supports_two_way(self) -> bool:
        """Messaging is outbound only.

        Slack and Teams are notification destinations, not stores. Pulling
        messages *into* the corpus would mean ingesting entire channels — a
        different product, and a privacy question nobody asked us to answer.
        """
        return self.kind is not ConnectorKind.MESSAGING


class ConnectorKind(StrEnum):
    CALENDAR = "calendar"
    TASKS = "tasks"
    MESSAGING = "messaging"
    DOCUMENTS = "documents"


class Direction(StrEnum):
    PULL = "pull"
    PUSH = "push"
    TWO_WAY = "two_way"

    @property
    def reads(self) -> bool:
        return self in (Direction.PULL, Direction.TWO_WAY)

    @property
    def writes(self) -> bool:
        return self in (Direction.PUSH, Direction.TWO_WAY)


@dataclass(frozen=True, slots=True)
class RemoteItem:
    """One object as the provider describes it, normalised.

    Deliberately flat and provider-agnostic. A Google event, a Graph task and a
    Notion page arrive as different shapes; every adapter flattens to this, so
    the sync engine below never learns which provider it is talking to.
    """

    external_id: str
    title: str
    body: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    due_at: datetime | None = None
    completed: bool = False
    url: str | None = None
    # Provider version marker — Google's etag, Graph's @odata.etag, Notion's
    # last_edited_time. Opaque, compared for equality only.
    etag: str | None = None
    updated_at: datetime | None = None
    deleted: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PullResult:
    items: tuple[RemoteItem, ...] = ()
    # The provider's own resume marker, stored verbatim. Decoding it would
    # couple us to a format the provider is free to change.
    cursor: str | None = None
    # False when the provider says the cursor expired and a full resync is
    # required. Google and Graph both do this after a period of inactivity.
    incremental: bool = True


class Resolution(StrEnum):
    """What the engine decided about one item."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DELETED = "deleted"
    SKIPPED = "skipped"
    # Both sides changed since the last sync. Not resolved: shown to the user.
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class SyncOutcome:
    resolution: Resolution
    reason: str = ""


def resolve(
    *,
    remote_etag: str | None,
    stored_etag: str | None,
    remote_updated_at: datetime | None,
    local_updated_at: datetime | None,
    last_pulled_at: datetime | None,
    remote_deleted: bool = False,
) -> SyncOutcome:
    """Decide what to do with one item. The heart of the engine.

    The four cases, and why the third is the only interesting one:

    1. **Neither side changed** — the etag matches what we stored. Skipped
       without a write, which is what makes an incremental sync cheap.
    2. **Only the remote changed** — apply it.
    3. **Both changed since we last looked** — a genuine conflict. *Not*
       resolved. Last-write-wins is what most integrations do here and it
       silently discards somebody's work; the row is flagged and the user
       decides.
    4. **Only the local changed** — nothing to pull; the push side will handle
       it if the connection is two-way.

    Deletion is checked first because a deleted remote object has no etag to
    compare and no timestamp worth trusting.
    """
    if remote_deleted:
        return SyncOutcome(Resolution.DELETED, "supprimé côté fournisseur")

    if stored_etag is None:
        return SyncOutcome(Resolution.CREATED, "nouvel élément")

    if remote_etag is not None and remote_etag == stored_etag:
        return SyncOutcome(Resolution.UNCHANGED, "inchangé")

    local_changed = (
        local_updated_at is not None
        and last_pulled_at is not None
        and local_updated_at > last_pulled_at
    )
    remote_changed = (
        remote_updated_at is not None
        and last_pulled_at is not None
        and remote_updated_at > last_pulled_at
    ) or remote_etag != stored_etag

    if local_changed and remote_changed:
        return SyncOutcome(
            Resolution.CONFLICT,
            "modifié des deux côtés depuis la dernière synchronisation",
        )
    if remote_changed:
        return SyncOutcome(Resolution.UPDATED, "modifié côté fournisseur")
    return SyncOutcome(Resolution.SKIPPED, "modifié localement uniquement")


# How long a connection is left failing before it stops being retried. Six
# consecutive failures over a five-minute cadence is half an hour of a token
# that is almost certainly revoked; retrying forever is how integrations
# generate support load and rate-limit bans.
MAX_CONSECUTIVE_FAILURES = 6


def backoff_seconds(consecutive_failures: int) -> int:
    """Exponential, capped at an hour.

    A provider having a bad minute must not be hammered, and a provider having a
    bad day must not be given up on within it.
    """
    return int(min(3600, 60 * (2 ** min(consecutive_failures, 6))))


class SyncConnectorPort(ABC):
    """One interface for seven destinations.

    Adapters implement only what their provider supports: `pull` raises
    `NotImplementedError` on Slack, which sends and does not store. The engine
    consults `Provider.supports_two_way` rather than catching that — a capability
    question answered by a property is clearer than one answered by an
    exception.
    """

    provider: Provider

    @abstractmethod
    async def pull(self, *, cursor: str | None = None) -> PullResult:
        """Fetch what changed since `cursor`."""

    @abstractmethod
    async def push(self, item: RemoteItem) -> RemoteItem:
        """Create or update an object, returning it with its id and etag.

        Returning the stored form matters: the etag it comes back with is what
        makes the *next* pull recognise our own write instead of treating it as
        a remote change and looping.
        """

    async def delete(self, external_id: str) -> None:  # pragma: no cover - default
        """Remove an object. Default is a no-op.

        Deliberately permissive: for several providers we would rather leave an
        orphan than risk deleting something a user created by hand in their own
        calendar.
        """
        return None

    async def health(self) -> bool:  # pragma: no cover - default
        return True
