"""Conflict resolution, and the seven connectors held to one contract.

`TestConflictResolution` is the file's subject. Last-write-wins is what most
integrations do and it silently discards somebody's work; the assertion that a
two-sided edit produces `CONFLICT` rather than `UPDATED` is the one that keeps
this one honest.

The connector tests are deliberately shallow on happy paths and sharp on the
edges providers actually produce: an expired cursor, a cancelled event, a
removed Graph object, a webhook with no id to link.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from app.domain.sync import (
    MAX_CONSECUTIVE_FAILURES,
    ConnectorKind,
    Direction,
    Provider,
    RemoteItem,
    Resolution,
    backoff_seconds,
    resolve,
)
from app.infra.sync.connectors import (
    ConnectorAuthError,
    ConnectorUnavailableError,
    GoogleCalendarConnector,
    MicrosoftGraphConnector,
    NotionConnector,
    ObsidianConnector,
    WebhookMessagingConnector,
)

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
EARLIER = NOW - timedelta(hours=2)
LATER = NOW + timedelta(hours=2)

GOOGLE_EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class TestProviders:
    def test_the_seven_required_providers_exist(self) -> None:
        assert {provider.value for provider in Provider} == {
            "google_calendar",
            "outlook_calendar",
            "microsoft_todo",
            "slack",
            "teams",
            "notion",
            "obsidian",
        }

    def test_obsidian_is_not_server_side(self) -> None:
        # A folder on somebody's disk. A scheduled server job for it would
        # never fire, so it must not be scheduled.
        assert not Provider.OBSIDIAN.is_server_side
        assert all(p.is_server_side for p in Provider if p is not Provider.OBSIDIAN)

    def test_messaging_is_outbound_only(self) -> None:
        # Pulling messages in would mean ingesting whole channels — a different
        # product and a privacy question nobody asked us to answer.
        assert not Provider.SLACK.supports_two_way
        assert not Provider.TEAMS.supports_two_way
        assert Provider.GOOGLE_CALENDAR.supports_two_way

    def test_each_provider_declares_its_kind(self) -> None:
        assert Provider.MICROSOFT_TODO.kind is ConnectorKind.TASKS
        assert Provider.NOTION.kind is ConnectorKind.DOCUMENTS
        assert all(provider.label for provider in Provider)


class TestDirection:
    def test_pull_reads_and_does_not_write(self) -> None:
        assert Direction.PULL.reads
        assert not Direction.PULL.writes

    def test_two_way_does_both(self) -> None:
        assert Direction.TWO_WAY.reads and Direction.TWO_WAY.writes


class TestConflictResolution:
    def test_a_new_item_is_created(self) -> None:
        outcome = resolve(
            remote_etag="e1",
            stored_etag=None,
            remote_updated_at=NOW,
            local_updated_at=None,
            last_pulled_at=None,
        )
        assert outcome.resolution is Resolution.CREATED

    def test_a_matching_etag_is_skipped_without_a_write(self) -> None:
        # What makes an incremental sync cheap.
        outcome = resolve(
            remote_etag="e1",
            stored_etag="e1",
            remote_updated_at=LATER,
            local_updated_at=None,
            last_pulled_at=NOW,
        )
        assert outcome.resolution is Resolution.UNCHANGED

    def test_a_remote_only_change_is_applied(self) -> None:
        outcome = resolve(
            remote_etag="e2",
            stored_etag="e1",
            remote_updated_at=LATER,
            local_updated_at=EARLIER,
            last_pulled_at=NOW,
        )
        assert outcome.resolution is Resolution.UPDATED

    def test_a_two_sided_edit_is_a_conflict_not_a_silent_overwrite(self) -> None:
        # The assertion this module exists for. Resolving it automatically is
        # what discards somebody's work without telling them.
        outcome = resolve(
            remote_etag="e2",
            stored_etag="e1",
            remote_updated_at=LATER,
            local_updated_at=LATER,
            last_pulled_at=NOW,
        )
        assert outcome.resolution is Resolution.CONFLICT
        assert "deux côtés" in outcome.reason

    def test_a_local_only_change_leaves_the_pull_alone(self) -> None:
        outcome = resolve(
            remote_etag="e1",
            stored_etag="e1",
            remote_updated_at=EARLIER,
            local_updated_at=LATER,
            last_pulled_at=NOW,
        )
        assert outcome.resolution is Resolution.UNCHANGED

    def test_deletion_wins_over_everything(self) -> None:
        # A deleted remote object has no etag to compare and no timestamp worth
        # trusting, so it is checked first.
        outcome = resolve(
            remote_etag=None,
            stored_etag="e1",
            remote_updated_at=None,
            local_updated_at=LATER,
            last_pulled_at=NOW,
            remote_deleted=True,
        )
        assert outcome.resolution is Resolution.DELETED

    def test_every_outcome_carries_a_reason(self) -> None:
        outcome = resolve(
            remote_etag="e2",
            stored_etag="e1",
            remote_updated_at=LATER,
            local_updated_at=None,
            last_pulled_at=NOW,
        )
        assert outcome.reason


class TestBackoff:
    def test_it_grows(self) -> None:
        assert backoff_seconds(0) < backoff_seconds(3) < backoff_seconds(6)

    def test_it_is_capped_at_an_hour(self) -> None:
        # A provider having a bad day must not be given up on within it, and
        # must not be hammered either.
        assert backoff_seconds(50) == 3600

    def test_the_give_up_threshold_is_stated(self) -> None:
        assert 3 <= MAX_CONSECUTIVE_FAILURES <= 10


class TestGoogleCalendar:
    def _connector(self) -> GoogleCalendarConnector:
        return GoogleCalendarConnector(token="tok")

    @pytest.mark.asyncio
    @respx.mock
    async def test_pulls_events_and_keeps_the_sync_token(self) -> None:
        respx.get(GOOGLE_EVENTS).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "e1",
                            "summary": "Comité",
                            "etag": '"123"',
                            "updated": "2026-08-03T10:00:00Z",
                            "start": {"dateTime": "2026-08-04T09:00:00Z"},
                            "end": {"dateTime": "2026-08-04T10:00:00Z"},
                        }
                    ],
                    "nextSyncToken": "SYNC1",
                },
            )
        )
        result = await self._connector().pull()

        assert result.items[0].title == "Comité"
        assert result.items[0].etag == '"123"'
        assert result.cursor == "SYNC1"
        assert result.incremental

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_cancelled_event_is_a_deletion(self) -> None:
        # Google marks deletions with a status rather than omitting the row,
        # which is what makes incremental deletion detection possible at all.
        respx.get(GOOGLE_EVENTS).mock(
            return_value=httpx.Response(200, json={"items": [{"id": "e1", "status": "cancelled"}]})
        )
        result = await self._connector().pull()
        assert result.items[0].deleted

    @pytest.mark.asyncio
    @respx.mock
    async def test_an_expired_cursor_asks_for_a_full_resync(self) -> None:
        # 410 is not an error, it is a protocol signal.
        respx.get(GOOGLE_EVENTS).mock(return_value=httpx.Response(410, json={}))
        result = await self._connector().pull(cursor="OLD")

        assert result.incremental is False
        assert result.cursor is None
        assert result.items == ()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_revoked_grant_is_distinguished_from_an_outage(self) -> None:
        # Retrying a revoked grant never succeeds; the connection must be
        # marked rather than retried forever.
        respx.get(GOOGLE_EVENTS).mock(return_value=httpx.Response(401, json={}))
        with pytest.raises(ConnectorAuthError):
            await self._connector().pull()

    @pytest.mark.asyncio
    @respx.mock
    async def test_rate_limiting_is_retryable(self) -> None:
        respx.get(GOOGLE_EVENTS).mock(return_value=httpx.Response(429, json={}))
        with pytest.raises(ConnectorUnavailableError) as caught:
            await self._connector().pull()
        assert not isinstance(caught.value, ConnectorAuthError)

    @pytest.mark.asyncio
    @respx.mock
    async def test_pushing_a_new_event_posts(self) -> None:
        route = respx.post(GOOGLE_EVENTS).mock(
            return_value=httpx.Response(200, json={"id": "new", "summary": "Point", "etag": '"9"'})
        )
        pushed = await self._connector().push(
            RemoteItem(external_id="", title="Point", starts_at=NOW)
        )
        assert route.called
        assert pushed.external_id == "new"
        # The returned etag is what stops the next pull treating our own write
        # as a remote change and looping.
        assert pushed.etag == '"9"'


class TestMicrosoftGraph:
    @pytest.mark.asyncio
    @respx.mock
    async def test_outlook_and_todo_share_one_client(self) -> None:
        respx.get(url__startswith="https://graph.microsoft.com/v1.0/me/calendarView/delta").mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "g1",
                            "subject": "Revue",
                            "@odata.etag": 'W/"1"',
                            "start": {"dateTime": "2026-08-04T09:00:00"},
                            "end": {"dateTime": "2026-08-04T10:00:00"},
                        }
                    ],
                    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/next",
                },
            )
        )
        connector = MicrosoftGraphConnector(token="tok", provider=Provider.OUTLOOK_CALENDAR)
        result = await connector.pull()

        assert result.items[0].title == "Revue"
        # A full URL, not a token. Stored verbatim and used as the next
        # request's URL.
        assert result.cursor == "https://graph.microsoft.com/v1.0/next"

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_removed_object_is_a_deletion(self) -> None:
        respx.get(url__startswith="https://graph.microsoft.com/v1.0/me/todo").mock(
            return_value=httpx.Response(
                200, json={"value": [{"id": "t1", "title": "x", "@removed": {"reason": "deleted"}}]}
            )
        )
        connector = MicrosoftGraphConnector(token="tok", provider=Provider.MICROSOFT_TODO)
        result = await connector.pull()
        assert result.items[0].deleted

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_completed_task_round_trips(self) -> None:
        respx.get(url__startswith="https://graph.microsoft.com/v1.0/me/todo").mock(
            return_value=httpx.Response(
                200, json={"value": [{"id": "t1", "title": "Fait", "status": "completed"}]}
            )
        )
        connector = MicrosoftGraphConnector(token="tok", provider=Provider.MICROSOFT_TODO)
        result = await connector.pull()
        assert result.items[0].completed


class TestMessaging:
    @pytest.mark.asyncio
    async def test_pulling_from_slack_raises_rather_than_returning_empty(self) -> None:
        # Returning empty would let a misconfigured two-way connection sit
        # there syncing nothing forever with no error.
        connector = WebhookMessagingConnector(
            webhook_url="https://hooks.slack.test/x", provider=Provider.SLACK
        )
        with pytest.raises(NotImplementedError):
            await connector.pull()

    @pytest.mark.asyncio
    @respx.mock
    async def test_slack_receives_blocks(self) -> None:
        route = respx.post("https://hooks.slack.test/x").mock(
            return_value=httpx.Response(200, text="ok")
        )
        connector = WebhookMessagingConnector(
            webhook_url="https://hooks.slack.test/x", provider=Provider.SLACK
        )
        await connector.push(RemoteItem(external_id="", title="Rappel", body="Corps"))

        body = route.calls[0].request.read()
        assert b"blocks" in body
        assert b"Rappel" in body

    @pytest.mark.asyncio
    @respx.mock
    async def test_teams_receives_a_message_card(self) -> None:
        # MessageCard rather than Adaptive Card: it is what an Incoming Webhook
        # accepts, including on the older desktop builds enterprises run.
        route = respx.post("https://outlook.test/hook").mock(
            return_value=httpx.Response(200, text="1")
        )
        connector = WebhookMessagingConnector(
            webhook_url="https://outlook.test/hook", provider=Provider.TEAMS
        )
        await connector.push(RemoteItem(external_id="", title="Rappel", url="https://x.test/e"))

        body = route.calls[0].request.read()
        assert b"MessageCard" in body
        assert b"OpenUri" in body

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_webhook_failure_is_reported(self) -> None:
        respx.post("https://hooks.slack.test/x").mock(return_value=httpx.Response(500))
        connector = WebhookMessagingConnector(
            webhook_url="https://hooks.slack.test/x", provider=Provider.SLACK
        )
        with pytest.raises(ConnectorUnavailableError):
            await connector.push(RemoteItem(external_id="", title="x"))


class TestNotion:
    @pytest.mark.asyncio
    @respx.mock
    async def test_the_cursor_is_an_edit_watermark(self) -> None:
        # Notion has no delta API, so the cursor holds the newest edit time
        # rather than an opaque provider token.
        respx.post("https://api.notion.com/v1/databases/db1/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "p1",
                            "url": "https://notion.so/p1",
                            "last_edited_time": "2026-08-03T10:00:00.000Z",
                            "properties": {
                                "Name": {"type": "title", "title": [{"plain_text": "Compte rendu"}]}
                            },
                        }
                    ]
                },
            )
        )
        result = await NotionConnector(token="tok", database_id="db1").pull()

        assert result.items[0].title == "Compte rendu"
        assert result.cursor == "2026-08-03T10:00:00.000Z"

    @pytest.mark.asyncio
    @respx.mock
    async def test_an_archived_page_is_a_deletion(self) -> None:
        respx.post("https://api.notion.com/v1/databases/db1/query").mock(
            return_value=httpx.Response(
                200, json={"results": [{"id": "p1", "archived": True, "properties": {}}]}
            )
        )
        result = await NotionConnector(token="tok", database_id="db1").pull()
        assert result.items[0].deleted


class TestObsidian:
    @pytest.mark.asyncio
    async def test_pulling_raises_because_it_is_a_folder(self) -> None:
        # Honest by construction: a server-side "Obsidian sync" that silently
        # does nothing is a feature that demos and is found inert months later.
        with pytest.raises(NotImplementedError):
            await ObsidianConnector().pull()

    @pytest.mark.asyncio
    async def test_pushing_renders_markdown_without_any_io(self) -> None:
        connector = ObsidianConnector(folder="Notes")
        rendered = await connector.push(
            RemoteItem(external_id="", title="Forecast Gabon", body="Trois hypothèses.")
        )

        assert rendered.body is not None
        assert rendered.body.startswith("---")
        assert "# Forecast Gabon" in rendered.body
        assert rendered.extra["path"] == "Notes/Forecast-Gabon.md"

    def test_front_matter_is_machine_readable(self) -> None:
        # Dataview and Obsidian's own queries read front matter, which makes an
        # exported note a first-class citizen of the vault.
        rendered = ObsidianConnector().render(RemoteItem(external_id="", title="Point", due_at=NOW))
        assert '"mindflow"' in rendered
        assert "due:" in rendered

    def test_the_filename_survives_windows(self) -> None:
        # A note that syncs everywhere except one laptop is worse than a note
        # with a duller name.
        rendered = ObsidianConnector().push
        assert rendered is not None
        from app.infra.sync.connectors import _slug

        assert _slug("Réunion: budget / Q3 <urgent>") == "Réunion-budget-Q3-urgent"
        assert _slug("") == "note"
