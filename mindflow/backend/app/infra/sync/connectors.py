"""Connector adapters for the seven destinations.

Same discipline as the AI adapters (ADR-045): no vendor SDK, plain HTTP through
`httpx`, and **one module that knows a provider's name** — the factory below.
A vendor SDK for each of seven services would be seven dependency trees, seven
release cadences and seven ways to be broken by an upgrade nobody asked for.

The grouping follows the *wire*, not the marketing:

* **Microsoft Graph serves both Outlook Calendar and To Do** from one API with
  one token. They share a class parameterised by resource path.
* **Google Calendar** has its own shape and its own incremental protocol
  (`syncToken`).
* **Slack and Teams are outbound only** — they post, they do not store. Their
  `pull` raises rather than returning empty, so a misconfiguration is loud.
* **Notion** is a document store whose "database" is a table of pages.
* **Obsidian is not a service at all.** It is a folder on somebody's disk. Its
  adapter renders Markdown and hands it back; the *client* writes the file. An
  adapter that pretended to sync it server-side would be a lie with a spinner.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.errors import ExtractionUnavailableError
from app.domain.sync import (
    Provider,
    PullResult,
    RemoteItem,
    SyncConnectorPort,
)
from app.observability.logging import get_logger

log = get_logger("sync.connector")

TIMEOUT = 30.0


class ConnectorUnavailableError(ExtractionUnavailableError):
    """The provider is unreachable or refusing.

    Subclasses the AI unavailability error deliberately: the worker's retry and
    backoff logic already treats that class as "try again later", and a second
    parallel taxonomy would be two things to keep in step.
    """

    code = "integration_unavailable"
    title = "Service externe indisponible"


def _parse_ts(value: str | None) -> datetime | None:
    """Provider timestamps, tolerantly.

    Three formats appear across these APIs: RFC 3339 with `Z`, with an offset,
    and Graph's naïve form. A parse failure returns None rather than raising —
    an unparseable timestamp degrades conflict detection for one item; an
    exception would fail the whole batch.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def _request(
    method: str,
    url: str,
    *,
    token: str,
    provider: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One HTTP call, with the failure taxonomy every connector shares."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "content-type": "application/json",
                },
                json=json_body,
                params=params,
            )
    except httpx.HTTPError as exc:
        log.warning("sync.transport_failed", provider=provider, error=type(exc).__name__)
        raise ConnectorUnavailableError("Service externe injoignable.") from exc

    if response.status_code in (401, 403):
        # Distinct from a transient failure: a revoked grant will never succeed
        # on retry, and the connection must be marked rather than retried
        # forever.
        log.warning("sync.unauthorised", provider=provider, status=response.status_code)
        raise ConnectorAuthError("Autorisation expirée ou révoquée.")
    if response.status_code == 429:
        raise ConnectorUnavailableError("Limite de débit atteinte chez le fournisseur.")
    if response.status_code == 410:
        # Google and Graph both use 410 to say "your cursor is too old". Not an
        # error — a signal to resync from scratch.
        raise CursorExpiredError("Le curseur de synchronisation a expiré.")
    if response.status_code >= 400:
        log.error("sync.failed", provider=provider, status=response.status_code)
        raise ConnectorUnavailableError("Échec de la synchronisation.")

    if not response.content:
        return {}
    payload: dict[str, Any] = response.json()
    return payload


class ConnectorAuthError(ConnectorUnavailableError):
    """The grant is gone. Retrying will not help; the user must reconnect."""

    code = "integration_unauthorised"
    title = "Reconnexion requise"


class CursorExpiredError(ConnectorUnavailableError):
    """The incremental cursor is too old. Resync fully."""

    code = "integration_cursor_expired"
    title = "Resynchronisation complète requise"


# --------------------------------------------------------------------------- #
# Google Calendar
# --------------------------------------------------------------------------- #
class GoogleCalendarConnector(SyncConnectorPort):
    """Google Calendar, via `syncToken` incremental sync.

    Google's protocol is the well-designed one of the set: a `syncToken`
    returned with every page, presented on the next call, and a 410 when it has
    aged out. That maps exactly onto `PullResult.incremental`.
    """

    provider = Provider.GOOGLE_CALENDAR
    BASE = "https://www.googleapis.com/calendar/v3"

    def __init__(self, *, token: str, calendar_id: str = "primary") -> None:
        self._token = token
        self._calendar = calendar_id

    async def pull(self, *, cursor: str | None = None) -> PullResult:
        params: dict[str, Any] = {"maxResults": 250, "singleEvents": True}
        if cursor:
            params["syncToken"] = cursor
        else:
            # A first sync without a window would pull a decade of history.
            params["timeMin"] = datetime.now(UTC).replace(microsecond=0).isoformat()

        try:
            payload = await _request(
                "GET",
                f"{self.BASE}/calendars/{self._calendar}/events",
                token=self._token,
                provider=self.provider.value,
                params=params,
            )
        except CursorExpiredError:
            # Reported rather than swallowed: the caller clears its cursor and
            # comes back for a full pass.
            return PullResult(items=(), cursor=None, incremental=False)

        items = tuple(_google_item(event) for event in payload.get("items", []))
        return PullResult(items=items, cursor=payload.get("nextSyncToken"), incremental=True)

    async def push(self, item: RemoteItem) -> RemoteItem:
        body: dict[str, Any] = {
            "summary": item.title,
            "description": item.body or "",
        }
        if item.starts_at:
            body["start"] = {"dateTime": item.starts_at.isoformat()}
            body["end"] = {"dateTime": (item.ends_at or item.starts_at).isoformat()}

        if item.external_id:
            payload = await _request(
                "PATCH",
                f"{self.BASE}/calendars/{self._calendar}/events/{item.external_id}",
                token=self._token,
                provider=self.provider.value,
                json_body=body,
            )
        else:
            payload = await _request(
                "POST",
                f"{self.BASE}/calendars/{self._calendar}/events",
                token=self._token,
                provider=self.provider.value,
                json_body=body,
            )
        return _google_item(payload)

    async def delete(self, external_id: str) -> None:
        await _request(
            "DELETE",
            f"{self.BASE}/calendars/{self._calendar}/events/{external_id}",
            token=self._token,
            provider=self.provider.value,
        )


def _google_item(event: dict[str, Any]) -> RemoteItem:
    start = event.get("start", {}) or {}
    end = event.get("end", {}) or {}
    return RemoteItem(
        external_id=str(event.get("id", "")),
        title=event.get("summary") or "(sans titre)",
        body=event.get("description"),
        starts_at=_parse_ts(start.get("dateTime") or start.get("date")),
        ends_at=_parse_ts(end.get("dateTime") or end.get("date")),
        url=event.get("htmlLink"),
        etag=event.get("etag"),
        updated_at=_parse_ts(event.get("updated")),
        # Google marks deletions with a status rather than omitting the row —
        # which is what makes incremental deletion detection possible at all.
        deleted=event.get("status") == "cancelled",
    )


# --------------------------------------------------------------------------- #
# Microsoft Graph — Outlook Calendar and To Do
# --------------------------------------------------------------------------- #
class MicrosoftGraphConnector(SyncConnectorPort):
    """Outlook Calendar and Microsoft To Do share one API and one token.

    Two products to a user, one integration to us. Splitting them into separate
    classes would have duplicated the delta protocol, the auth handling and the
    error mapping to express a difference that is one URL path.
    """

    BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, *, token: str, provider: Provider, list_id: str | None = None) -> None:
        self.provider = provider
        self._token = token
        self._list_id = list_id

    @property
    def _path(self) -> str:
        if self.provider is Provider.OUTLOOK_CALENDAR:
            return "/me/calendarView/delta"
        target = self._list_id or "tasks"
        return f"/me/todo/lists/{target}/tasks/delta"

    async def pull(self, *, cursor: str | None = None) -> PullResult:
        url = cursor or f"{self.BASE}{self._path}"
        params: dict[str, Any] = {}
        if not cursor and self.provider is Provider.OUTLOOK_CALENDAR:
            now = datetime.now(UTC).replace(microsecond=0)
            params = {
                "startDateTime": now.isoformat(),
                "endDateTime": now.replace(year=now.year + 1).isoformat(),
            }

        try:
            payload = await _request(
                "GET", url, token=self._token, provider=self.provider.value, params=params or None
            )
        except CursorExpiredError:
            return PullResult(items=(), cursor=None, incremental=False)

        convert = _graph_event if self.provider is Provider.OUTLOOK_CALENDAR else _graph_task
        items = tuple(convert(row) for row in payload.get("value", []))
        # Graph hands back a full URL, not a token. Stored verbatim and used as
        # the next request's URL — decoding it would couple us to its format.
        return PullResult(
            items=items,
            cursor=payload.get("@odata.deltaLink") or payload.get("@odata.nextLink"),
            incremental=True,
        )

    async def push(self, item: RemoteItem) -> RemoteItem:
        if self.provider is Provider.OUTLOOK_CALENDAR:
            body: dict[str, Any] = {
                "subject": item.title,
                "body": {"contentType": "text", "content": item.body or ""},
            }
            if item.starts_at:
                body["start"] = {"dateTime": item.starts_at.isoformat(), "timeZone": "UTC"}
                body["end"] = {
                    "dateTime": (item.ends_at or item.starts_at).isoformat(),
                    "timeZone": "UTC",
                }
            collection = "/me/events"
            convert = _graph_event
        else:
            body = {
                "title": item.title,
                "body": {"contentType": "text", "content": item.body or ""},
                "status": "completed" if item.completed else "notStarted",
            }
            if item.due_at:
                body["dueDateTime"] = {
                    "dateTime": item.due_at.isoformat(),
                    "timeZone": "UTC",
                }
            collection = f"/me/todo/lists/{self._list_id or 'tasks'}/tasks"
            convert = _graph_task

        if item.external_id:
            payload = await _request(
                "PATCH",
                f"{self.BASE}{collection}/{item.external_id}",
                token=self._token,
                provider=self.provider.value,
                json_body=body,
            )
        else:
            payload = await _request(
                "POST",
                f"{self.BASE}{collection}",
                token=self._token,
                provider=self.provider.value,
                json_body=body,
            )
        return convert(payload)


def _graph_event(row: dict[str, Any]) -> RemoteItem:
    start = row.get("start", {}) or {}
    end = row.get("end", {}) or {}
    return RemoteItem(
        external_id=str(row.get("id", "")),
        title=row.get("subject") or "(sans titre)",
        body=(row.get("body") or {}).get("content"),
        starts_at=_parse_ts(start.get("dateTime")),
        ends_at=_parse_ts(end.get("dateTime")),
        url=row.get("webLink"),
        etag=row.get("@odata.etag"),
        updated_at=_parse_ts(row.get("lastModifiedDateTime")),
        deleted="@removed" in row,
    )


def _graph_task(row: dict[str, Any]) -> RemoteItem:
    due = row.get("dueDateTime", {}) or {}
    return RemoteItem(
        external_id=str(row.get("id", "")),
        title=row.get("title") or "(sans titre)",
        body=(row.get("body") or {}).get("content"),
        due_at=_parse_ts(due.get("dateTime")),
        completed=row.get("status") == "completed",
        etag=row.get("@odata.etag"),
        updated_at=_parse_ts(row.get("lastModifiedDateTime")),
        deleted="@removed" in row,
    )


# --------------------------------------------------------------------------- #
# Slack and Teams — outbound only
# --------------------------------------------------------------------------- #
class WebhookMessagingConnector(SyncConnectorPort):
    """Slack and Teams, as notification destinations.

    `pull` raises rather than returning empty. Returning empty would let a
    misconfigured two-way connection sit there syncing nothing, forever, with no
    error — the failure mode that takes a week to notice.

    Pulling messages *in* is deliberately not implemented: it would mean
    ingesting entire channels into somebody's personal corpus, which is a
    different product and a privacy question nobody asked us to answer.
    """

    def __init__(self, *, webhook_url: str, provider: Provider) -> None:
        self.provider = provider
        self._url = webhook_url

    async def pull(self, *, cursor: str | None = None) -> PullResult:
        raise NotImplementedError(
            f"{self.provider.label} est une destination sortante : rien à récupérer."
        )

    async def push(self, item: RemoteItem) -> RemoteItem:
        body = _slack_body(item) if self.provider is Provider.SLACK else _teams_body(item)
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Incoming webhooks are unauthenticated by URL — the URL is the
                # secret — so this does not go through `_request`.
                response = await client.post(self._url, json=body)
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError("Service de messagerie injoignable.") from exc

        if response.status_code >= 400:
            log.error(
                "sync.webhook_failed", provider=self.provider.value, status=response.status_code
            )
            raise ConnectorUnavailableError("Échec de l'envoi du message.")

        # A webhook returns no identifier, so there is nothing to link. Echoing
        # the item back keeps the port's contract without inventing an id that
        # a later sync would try to match.
        return item


def _slack_body(item: RemoteItem) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{item.title}*"}}
    ]
    if item.body:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": item.body[:2900]}})
    if item.url:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"<{item.url}|Ouvrir dans MindFlow>"}],
            }
        )
    return {"text": item.title, "blocks": blocks}


def _teams_body(item: RemoteItem) -> dict[str, Any]:
    # MessageCard rather than Adaptive Card: it is what an Incoming Webhook
    # connector accepts, and it renders in every Teams client including the
    # older desktop builds enterprises still run.
    card: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": item.title,
        "themeColor": "5B67F5",
        "title": item.title,
        "text": item.body or "",
    }
    if item.url:
        card["potentialAction"] = [
            {
                "@type": "OpenUri",
                "name": "Ouvrir dans MindFlow",
                "targets": [{"os": "default", "uri": item.url}],
            }
        ]
    return card


# --------------------------------------------------------------------------- #
# Notion
# --------------------------------------------------------------------------- #
class NotionConnector(SyncConnectorPort):
    """A Notion database, treated as a table of pages.

    Notion has no delta API. Incremental sync is done by querying sorted on
    `last_edited_time` and stopping at the stored watermark — which is what the
    cursor holds here, unlike Google and Graph where it is an opaque provider
    token.
    """

    provider = Provider.NOTION
    BASE = "https://api.notion.com/v1"
    VERSION = "2022-06-28"

    def __init__(self, *, token: str, database_id: str) -> None:
        self._token = token
        self._database = database_id

    async def pull(self, *, cursor: str | None = None) -> PullResult:
        body: dict[str, Any] = {
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "page_size": 100,
        }
        if cursor:
            body["filter"] = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"after": cursor},
            }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    f"{self.BASE}/databases/{self._database}/query",
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Notion-Version": self.VERSION,
                        "content-type": "application/json",
                    },
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError("Notion injoignable.") from exc

        if response.status_code in (401, 403):
            raise ConnectorAuthError("Autorisation Notion expirée.")
        if response.status_code >= 400:
            raise ConnectorUnavailableError("Échec de la synchronisation Notion.")

        payload = response.json()
        rows = payload.get("results", [])
        items = tuple(_notion_item(row) for row in rows)
        # The watermark is the newest edit we saw. Stored as the cursor, so the
        # next pass asks for strictly later edits.
        newest = rows[0].get("last_edited_time") if rows else cursor
        return PullResult(items=items, cursor=newest, incremental=True)

    async def push(self, item: RemoteItem) -> RemoteItem:
        properties: dict[str, Any] = {"Name": {"title": [{"text": {"content": item.title[:2000]}}]}}
        body: dict[str, Any] = {"properties": properties}
        if not item.external_id:
            body["parent"] = {"database_id": self._database}
        if item.body:
            body["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": item.body[:1900]}}]
                    },
                }
            ]

        url = f"{self.BASE}/pages/{item.external_id}" if item.external_id else f"{self.BASE}/pages"
        method = "PATCH" if item.external_id else "POST"

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.request(
                    method,
                    url,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Notion-Version": self.VERSION,
                        "content-type": "application/json",
                    },
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError("Notion injoignable.") from exc

        if response.status_code >= 400:
            raise ConnectorUnavailableError("Échec de l'écriture dans Notion.")
        return _notion_item(response.json())


def _notion_item(page: dict[str, Any]) -> RemoteItem:
    properties = page.get("properties", {}) or {}
    title = "(sans titre)"
    for value in properties.values():
        if value.get("type") == "title":
            parts = value.get("title", [])
            if parts:
                title = "".join(part.get("plain_text", "") for part in parts) or title
            break
    edited = page.get("last_edited_time")
    return RemoteItem(
        external_id=str(page.get("id", "")),
        title=title,
        url=page.get("url"),
        # Notion has no etag; the edit timestamp is the version marker, which
        # is why it appears in both fields.
        etag=edited,
        updated_at=_parse_ts(edited),
        deleted=bool(page.get("archived")),
    )


# --------------------------------------------------------------------------- #
# Obsidian — not a service
# --------------------------------------------------------------------------- #
class ObsidianConnector(SyncConnectorPort):
    """A vault on somebody's disk, which the server cannot reach.

    This adapter renders Markdown with YAML front matter and hands it back. The
    *client* writes the file. Everything about it is deliberately honest: `pull`
    raises, `push` performs no I/O, and `Provider.is_server_side` is False so no
    scheduled job ever tries to run it.

    The alternative — a server-side "Obsidian sync" that silently does nothing —
    is the kind of feature that ships, demos, and is discovered to be inert
    three months later.
    """

    provider = Provider.OBSIDIAN

    def __init__(self, *, folder: str = "MindFlow") -> None:
        self._folder = folder

    async def pull(self, *, cursor: str | None = None) -> PullResult:
        raise NotImplementedError(
            "Obsidian est un dossier local : la synchronisation se fait côté client."
        )

    async def push(self, item: RemoteItem) -> RemoteItem:
        return RemoteItem(
            external_id=item.external_id or _slug(item.title),
            title=item.title,
            body=self.render(item),
            etag=None,
            extra={"path": f"{self._folder}/{_slug(item.title)}.md"},
        )

    def render(self, item: RemoteItem) -> str:
        """Markdown with front matter, the way a vault expects it.

        Front matter rather than inline metadata because Obsidian's own queries
        and the Dataview plugin both read it, which makes an exported note a
        first-class citizen of the vault rather than a text dump.
        """
        front: dict[str, Any] = {"source": "mindflow", "title": item.title}
        if item.due_at:
            front["due"] = item.due_at.date().isoformat()
        if item.starts_at:
            front["date"] = item.starts_at.date().isoformat()
        if item.url:
            front["url"] = item.url

        lines = ["---"]
        lines += [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in front.items()]
        lines += ["---", "", f"# {item.title}", ""]
        if item.body:
            lines.append(item.body)
        return "\n".join(lines)


def _slug(title: str) -> str:
    """A filename a vault will accept on every platform.

    Windows forbids a set of characters macOS and Linux allow, so the strictest
    of the three wins — a note that syncs everywhere except one laptop is worse
    than a note with a slightly duller name.
    """
    # Forbidden characters become *spaces*, not dashes, so that `budget / Q3`
    # yields `budget-Q3` rather than `budget---Q3`: runs collapse when the
    # words are rejoined.
    cleaned = "".join(char if char.isalnum() or char in " -_" else " " for char in title)
    return "-".join(cleaned.split()).strip("-")[:100] or "note"
