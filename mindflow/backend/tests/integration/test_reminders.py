"""Reminders and notifications, end to end — including the dispatcher.

The properties asserted here are the ones that make a notification system
trustworthy rather than annoying: nothing fires twice, nothing is silently
dropped, a completed task stops nagging, and a push failure never costs the user
the notification itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.config import Settings
from app.domain.enums import PushProvider, ReminderStatus
from app.infra.db.models.core import Notification, Reminder
from app.infra.db.session import privileged_session
from app.infra.push.factory import build_push_sender, reset_senders
from app.workers.scheduled.reminder_dispatcher import dispatch_due_reminders
from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def _task_with_due(
    client: AsyncClient, headers: dict[str, str], *, title: str = "Rappeler le DAF"
) -> dict:
    response = await client.post(
        "/v1/entries",
        headers=headers,
        json={"entry_type": "task", "title": title, "due_expression": "demain"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _force_due(reminder_id: str) -> None:
    """Pull a reminder into the past so the dispatcher will claim it."""
    async with privileged_session() as session:
        await session.execute(
            text("UPDATE reminder SET remind_at = now() - interval '1 minute' WHERE id = :id"),
            {"id": reminder_id},
        )


class TestAutomaticScheduling:
    async def test_a_due_date_schedules_reminders(self, client: AsyncClient, auth_headers) -> None:
        """A deadline nobody is told about is a deadline that gets missed."""
        entry = await _task_with_due(client, auth_headers)

        response = await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)

        reminders = response.json()["data"]
        assert reminders, "a task with a due date must get automatic reminders"
        assert all(item["offset_rule"] is not None for item in reminders)

    async def test_rescheduling_rewrites_the_automatic_set(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        before = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]

        new_due = (datetime.now(UTC) + timedelta(days=20)).isoformat()
        await client.post(
            f"/v1/entries/{entry['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": new_due},
        )

        after = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        scheduled = [item for item in after if item["status"] == "scheduled"]
        assert scheduled
        assert {item["remind_at"] for item in scheduled} != {
            item["remind_at"] for item in before if item["status"] == "scheduled"
        }

    async def test_rescheduling_leaves_a_manual_reminder_alone(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """The user asked for that moment. It is not the scheduler's to revise."""
        entry = await _task_with_due(client, auth_headers)
        manual_at = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)
        created = await client.post(
            "/v1/reminders",
            headers=auth_headers,
            json={"entry_id": entry["id"], "remind_at": manual_at.isoformat()},
        )
        assert created.status_code == 201
        manual_id = created.json()["data"]["id"]

        await client.post(
            f"/v1/entries/{entry['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": (datetime.now(UTC) + timedelta(days=30)).isoformat()},
        )

        after = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        manual = next(item for item in after if item["id"] == manual_id)
        assert manual["status"] == "scheduled"

    async def test_completing_a_task_cancels_its_reminders(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """A phone buzzing about something already done is the fastest way to
        get notifications switched off for good."""
        entry = await _task_with_due(client, auth_headers)
        await client.post(f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers)

        after = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        assert all(item["status"] != "scheduled" for item in after)

    async def test_deleting_a_task_cancels_its_reminders(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        await client.delete(f"/v1/entries/{entry['id']}", headers=auth_headers)

        async with privileged_session() as session:
            rows = (
                (
                    await session.execute(
                        select(Reminder).where(Reminder.entry_id == uuid.UUID(entry["id"]))
                    )
                )
                .scalars()
                .all()
            )
        assert all(row.status != ReminderStatus.SCHEDULED.value for row in rows)


class TestManualReminders:
    async def test_create_and_cancel(self, client: AsyncClient, auth_headers) -> None:
        entry = await _task_with_due(client, auth_headers)
        moment = (datetime.now(UTC) + timedelta(hours=5)).replace(microsecond=0)

        created = await client.post(
            "/v1/reminders",
            headers=auth_headers,
            json={"entry_id": entry["id"], "remind_at": moment.isoformat()},
        )
        assert created.status_code == 201
        reminder_id = created.json()["data"]["id"]

        await client.delete(f"/v1/reminders/{reminder_id}", headers=auth_headers)

        listed = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        assert next(item for item in listed if item["id"] == reminder_id)["status"] == "cancelled"

    async def test_an_instant_in_the_past_is_refused(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        response = await client.post(
            "/v1/reminders",
            headers=auth_headers,
            json={"entry_id": entry["id"], "remind_at": past},
        )
        assert response.status_code == 422

    async def test_an_offset_rule_resolves_against_the_due_date(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        response = await client.post(
            "/v1/reminders",
            headers=auth_headers,
            json={"entry_id": entry["id"], "offset_rule": "-2h"},
        )
        assert response.status_code == 201

    async def test_an_offset_without_a_deadline_is_refused(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = (
            await client.post(
                "/v1/entries",
                headers=auth_headers,
                json={"entry_type": "task", "title": "Sans échéance"},
            )
        ).json()["data"]

        response = await client.post(
            "/v1/reminders",
            headers=auth_headers,
            json={"entry_id": entry["id"], "offset_rule": "-2h"},
        )
        assert response.status_code == 422

    async def test_reminders_are_scoped_to_the_caller(
        self, client: AsyncClient, auth_headers, other_auth_headers
    ) -> None:
        await _task_with_due(client, auth_headers)
        response = await client.get("/v1/reminders", headers=other_auth_headers)
        assert response.json()["data"] == []


class TestDevices:
    async def test_registration_is_idempotent_on_install_id(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Keyed on the installation, not on the push token — tokens rotate, and
        keying on one sends the same reminder five times to a single phone."""
        payload = {
            "install_id": "install-0000000001",
            "platform": "android",
            "push_token": "token-a",
            "push_provider": "fcm",
        }
        first = await client.put("/v1/devices", headers=auth_headers, json=payload)
        second = await client.put(
            "/v1/devices", headers=auth_headers, json={**payload, "push_token": "token-b"}
        )

        assert first.status_code == 200
        assert second.json()["data"]["id"] == first.json()["data"]["id"]

        listed = await client.get("/v1/devices", headers=auth_headers)
        assert len(listed.json()["data"]) == 1

    async def test_the_push_token_is_never_echoed_back(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """It is a delivery credential; an endpoint that returns it turns a
        read-only leak into a spoofing capability."""
        response = await client.put(
            "/v1/devices",
            headers=auth_headers,
            json={
                "install_id": "install-0000000002",
                "platform": "windows",
                "push_token": "https://db5.notify.windows.com/secret",
                "push_provider": "wns",
            },
        )
        assert "secret" not in response.text
        assert response.json()["data"]["push_enabled"] is True

    async def test_windows_is_an_accepted_platform(self, client: AsyncClient, auth_headers) -> None:
        response = await client.put(
            "/v1/devices",
            headers=auth_headers,
            json={
                "install_id": "install-0000000003",
                "platform": "windows",
                "push_provider": "local",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["platform"] == "windows"

    async def test_revocation(self, client: AsyncClient, auth_headers) -> None:
        await client.put(
            "/v1/devices",
            headers=auth_headers,
            json={
                "install_id": "install-0000000004",
                "platform": "ios",
                "push_token": "t",
                "push_provider": "fcm",
            },
        )
        await client.delete("/v1/devices/install-0000000004", headers=auth_headers)
        listed = await client.get("/v1/devices", headers=auth_headers)
        assert listed.json()["data"] == []


class TestDispatcher:
    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_senders()

    async def test_fires_a_due_reminder_and_writes_a_notification(
        self, client: AsyncClient, auth_headers, api_settings: Settings
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        await _force_due(reminders[0]["id"])

        sent = await dispatch_due_reminders(api_settings)

        assert sent == 1
        centre = (await client.get("/v1/notifications", headers=auth_headers)).json()["data"]
        assert centre["unread"] == 1
        assert centre["items"][0]["kind"] == "reminder"
        assert centre["items"][0]["entry_id"] == entry["id"]

    async def test_never_fires_the_same_reminder_twice(
        self, client: AsyncClient, auth_headers, api_settings: Settings
    ) -> None:
        """The claim and the status flip happen in one transaction, so a second
        pass — or a second worker — finds nothing to do."""
        entry = await _task_with_due(client, auth_headers)
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        await _force_due(reminders[0]["id"])

        first = await dispatch_due_reminders(api_settings)
        second = await dispatch_due_reminders(api_settings)

        assert first == 1
        assert second == 0
        centre = (await client.get("/v1/notifications", headers=auth_headers)).json()["data"]
        assert centre["unread"] == 1

    async def test_a_missed_window_is_recorded_not_left_scheduled(
        self, client: AsyncClient, auth_headers, api_settings: Settings
    ) -> None:
        """Left scheduled, it would fire at a random moment weeks later."""
        entry = await _task_with_due(client, auth_headers)
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        async with privileged_session() as session:
            await session.execute(
                text("UPDATE reminder SET remind_at = now() - interval '3 days' WHERE id = :id"),
                {"id": reminders[0]["id"]},
            )

        sent = await dispatch_due_reminders(api_settings)

        assert sent == 0
        async with privileged_session() as session:
            reminder = await session.get(Reminder, uuid.UUID(reminders[0]["id"]))
            assert reminder is not None
            assert reminder.status == ReminderStatus.FAILED.value
            assert reminder.last_error == "missed_window"

    async def test_a_deleted_subject_produces_no_notification(
        self, client: AsyncClient, auth_headers, api_settings: Settings
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        await _force_due(reminders[0]["id"])
        async with privileged_session() as session:
            await session.execute(
                text("UPDATE entry SET deleted_at = now() WHERE id = :id"),
                {"id": entry["id"]},
            )

        sent = await dispatch_due_reminders(api_settings)

        assert sent == 0

    async def test_the_notification_survives_a_push_failure(
        self, client: AsyncClient, auth_headers, api_settings: Settings
    ) -> None:
        """The row is the durable record; the push is a courtesy. Recording only
        on a successful push loses exactly the notifications that mattered."""
        await client.put(
            "/v1/devices",
            headers=auth_headers,
            json={
                "install_id": "install-0000000099",
                "platform": "android",
                "push_token": "dead-token",
                "push_provider": "fcm",
            },
        )
        sender = build_push_sender(api_settings, PushProvider.FCM)
        assert sender is not None
        sender.fail_with = "boom"  # type: ignore[attr-defined]

        entry = await _task_with_due(client, auth_headers)
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        await _force_due(reminders[0]["id"])

        sent = await dispatch_due_reminders(api_settings)

        assert sent == 1
        centre = (await client.get("/v1/notifications", headers=auth_headers)).json()["data"]
        assert centre["unread"] == 1
        assert centre["items"][0]["payload"]["entry_id"] == entry["id"]

    async def test_pushes_to_a_registered_device(
        self, client: AsyncClient, auth_headers, api_settings: Settings
    ) -> None:
        await client.put(
            "/v1/devices",
            headers=auth_headers,
            json={
                "install_id": "install-0000000098",
                "platform": "android",
                "push_token": "live-token",
                "push_provider": "fcm",
            },
        )
        entry = await _task_with_due(client, auth_headers, title="Appeler la banque")
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        await _force_due(reminders[0]["id"])

        await dispatch_due_reminders(api_settings)

        sender = build_push_sender(api_settings, PushProvider.FCM)
        assert sender is not None
        assert sender.sent  # type: ignore[attr-defined]
        message = sender.sent[-1].message  # type: ignore[attr-defined]
        assert message.title == "Appeler la banque"
        assert message.data["entry_id"] == entry["id"]
        # Collapsed per entry: a second reminder replaces the first on the lock
        # screen instead of stacking.
        assert message.collapse_key == f"entry-{entry['id']}"


class TestNotificationCentre:
    async def test_mark_read_and_read_all(
        self, client: AsyncClient, auth_headers, api_settings: Settings
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        await _force_due(reminders[0]["id"])
        await dispatch_due_reminders(api_settings)

        centre = (await client.get("/v1/notifications", headers=auth_headers)).json()["data"]
        notification_id = centre["items"][0]["id"]

        await client.post(f"/v1/notifications/{notification_id}/read", headers=auth_headers)
        after = (await client.get("/v1/notifications", headers=auth_headers)).json()["data"]
        assert after["unread"] == 0

        await client.post("/v1/notifications/read-all", headers=auth_headers)
        assert (await client.get("/v1/notifications", headers=auth_headers)).json()["data"][
            "unread"
        ] == 0

    async def test_notifications_are_scoped_to_the_caller(
        self, client: AsyncClient, auth_headers, other_auth_headers, api_settings: Settings
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        await _force_due(reminders[0]["id"])
        await dispatch_due_reminders(api_settings)

        response = await client.get("/v1/notifications", headers=other_auth_headers)
        assert response.json()["data"]["items"] == []

    async def test_unread_filter(
        self, client: AsyncClient, auth_headers, api_settings: Settings
    ) -> None:
        entry = await _task_with_due(client, auth_headers)
        reminders = (
            await client.get(f"/v1/reminders?entry_id={entry['id']}", headers=auth_headers)
        ).json()["data"]
        await _force_due(reminders[0]["id"])
        await dispatch_due_reminders(api_settings)

        response = await client.get("/v1/notifications?unread_only=true", headers=auth_headers)
        assert len(response.json()["data"]["items"]) == 1

        async with privileged_session() as session:
            count = (await session.execute(select(Notification).limit(5))).scalars().all()
        assert count
