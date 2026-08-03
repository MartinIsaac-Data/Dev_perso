"""Planning end to end: subtasks, recurrence, snoozing, agenda, calendar, bulk.

Runs against the real API and a real PostgreSQL. The behaviours asserted here
are the ones a user would notice being wrong — a recurring task that drifts, a
snooze that silently moved a deadline, an agenda that puts an item on the wrong
day.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def _create_task(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    title: str = "Rappeler le DAF",
    due_expression: str | None = None,
) -> dict:
    response = await client.post(
        "/v1/entries",
        headers=headers,
        json={
            "entry_type": "task",
            "title": title,
            **({"due_expression": due_expression} if due_expression else {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


class TestSubtasks:
    async def test_add_list_and_complete(self, client: AsyncClient, auth_headers) -> None:
        entry = await _create_task(client, auth_headers)

        created = await client.post(
            f"/v1/entries/{entry['id']}/subtasks",
            headers=auth_headers,
            json={"title": "Préparer les chiffres"},
        )
        assert created.status_code == 201
        subtask = created.json()["data"]

        checked = await client.patch(
            f"/v1/subtasks/{subtask['id']}", headers=auth_headers, json={"completed": True}
        )
        assert checked.status_code == 200
        assert checked.json()["data"]["completed_at"] is not None

        listed = await client.get(f"/v1/entries/{entry['id']}/subtasks", headers=auth_headers)
        assert len(listed.json()["data"]) == 1

    async def test_reorder_is_idempotent(self, client: AsyncClient, auth_headers) -> None:
        """Sending the full ordered list, twice, gives the same order.

        Drag-and-drop on a flaky connection emits deltas out of order; replaying
        two of them against a shared list gives an order nobody asked for.
        """
        entry = await _create_task(client, auth_headers)
        ids = []
        for title in ("A", "B", "C"):
            response = await client.post(
                f"/v1/entries/{entry['id']}/subtasks",
                headers=auth_headers,
                json={"title": title},
            )
            ids.append(response.json()["data"]["id"])

        reversed_ids = list(reversed(ids))
        for _ in range(2):
            response = await client.post(
                f"/v1/entries/{entry['id']}/subtasks/reorder",
                headers=auth_headers,
                json={"ordered_ids": reversed_ids},
            )
            assert response.status_code == 200
            assert [item["title"] for item in response.json()["data"]] == ["C", "B", "A"]

    async def test_an_empty_title_is_refused(self, client: AsyncClient, auth_headers) -> None:
        entry = await _create_task(client, auth_headers)
        response = await client.post(
            f"/v1/entries/{entry['id']}/subtasks", headers=auth_headers, json={"title": "   "}
        )
        assert response.status_code == 422

    async def test_subtasks_of_another_tenant_are_invisible(
        self, client: AsyncClient, auth_headers, other_auth_headers
    ) -> None:
        entry = await _create_task(client, auth_headers)
        await client.post(
            f"/v1/entries/{entry['id']}/subtasks",
            headers=auth_headers,
            json={"title": "Secret"},
        )
        response = await client.get(
            f"/v1/entries/{entry['id']}/subtasks", headers=other_auth_headers
        )
        assert response.json()["data"] == []


class TestRecurrence:
    async def test_completing_a_recurring_task_creates_the_next_occurrence(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _create_task(client, auth_headers, due_expression="demain")

        rule = await client.post(
            f"/v1/entries/{entry['id']}/recurrence",
            headers=auth_headers,
            json={"rule": "FREQ=WEEKLY"},
        )
        assert rule.status_code == 200

        completed = await client.post(
            f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers
        )
        assert completed.status_code == 200
        body = completed.json()["data"]

        assert body["entry"]["status"] == "done"
        assert body["next_occurrence"] is not None
        assert body["next_occurrence"]["title"] == entry["title"]
        assert body["next_occurrence"]["id"] != entry["id"]
        assert body["next_occurrence"]["task"]["due_at"] is not None

    async def test_a_non_recurring_task_produces_no_successor(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _create_task(client, auth_headers, due_expression="demain")
        completed = await client.post(
            f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers
        )
        assert completed.json()["data"]["next_occurrence"] is None

    async def test_an_unsupported_rule_is_refused_not_approximated(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """A task appearing on a day nobody asked for is worse than a rule that
        does not apply."""
        entry = await _create_task(client, auth_headers)
        response = await client.post(
            f"/v1/entries/{entry['id']}/recurrence",
            headers=auth_headers,
            json={"rule": "FREQ=HOURLY"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_failed"

    async def test_the_successor_carries_no_capture_link(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """The audio documents the first occurrence, not the twentieth. Keeping
        the link would make one recording look like the source of a hundred
        tasks."""
        entry = await _create_task(client, auth_headers, due_expression="demain")
        await client.post(
            f"/v1/entries/{entry['id']}/recurrence",
            headers=auth_headers,
            json={"rule": "FREQ=DAILY"},
        )
        completed = await client.post(
            f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers
        )
        successor = completed.json()["data"]["next_occurrence"]
        assert successor["source"]["capture_id"] is None


class TestSnoozeAndReschedule:
    async def test_snooze_hides_without_moving_the_deadline(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """ "I don't want to see this until Thursday" and "this is due Thursday"
        are different statements. Conflating them rewrites the user's
        commitments."""
        entry = await _create_task(client, auth_headers, due_expression="demain")
        original_due = entry["task"]["due_at"]

        until = (datetime.now(UTC) + timedelta(days=2)).isoformat()
        response = await client.post(
            f"/v1/entries/{entry['id']}/snooze",
            headers=auth_headers,
            json={"until": until},
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["status"] == "snoozed"
        assert body["task"]["due_at"] == original_due

    async def test_snoozing_into_the_past_is_refused(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _create_task(client, auth_headers)
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        response = await client.post(
            f"/v1/entries/{entry['id']}/snooze", headers=auth_headers, json={"until": past}
        )
        assert response.status_code == 422

    async def test_reschedule_moves_the_deadline_and_drops_the_stale_wording(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Keeping "jeudi" next to a date the user has since dragged elsewhere
        is misleading."""
        entry = await _create_task(client, auth_headers, due_expression="jeudi")
        assert entry["task"]["due_raw_expression"] == "jeudi"

        new_due = (datetime.now(UTC) + timedelta(days=10)).isoformat()
        response = await client.post(
            f"/v1/entries/{entry['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": new_due},
        )

        body = response.json()["data"]
        assert body["task"]["due_raw_expression"] is None
        assert body["task"]["due_at"] is not None

    async def test_clearing_a_deadline_is_allowed(self, client: AsyncClient, auth_headers) -> None:
        entry = await _create_task(client, auth_headers, due_expression="demain")
        response = await client.post(
            f"/v1/entries/{entry['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": None},
        )
        assert response.json()["data"]["task"]["due_at"] is None

    async def test_reopen_clears_the_completion(self, client: AsyncClient, auth_headers) -> None:
        entry = await _create_task(client, auth_headers)
        await client.post(f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers)
        response = await client.post(f"/v1/entries/{entry['id']}/reopen", headers=auth_headers)
        body = response.json()["data"]
        assert body["status"] == "active"
        assert body["task"]["completed_at"] is None


class TestAgenda:
    async def test_returns_the_requested_window(self, client: AsyncClient, auth_headers) -> None:
        await _create_task(client, auth_headers, due_expression="demain")

        response = await client.get("/v1/agenda?view=week", headers=auth_headers)

        assert response.status_code == 200
        agenda = response.json()["data"]
        assert agenda["view"] == "week"
        assert len(agenda["days"]) == 7
        assert sum(len(day["items"]) for day in agenda["days"]) >= 1

    async def test_a_day_view_spans_one_day(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get("/v1/agenda?view=day", headers=auth_headers)
        assert len(response.json()["data"]["days"]) == 1

    async def test_a_month_view_covers_whole_weeks(self, client: AsyncClient, auth_headers) -> None:
        """The grid shows whole weeks; anything else leaves holes at the corners
        of the calendar."""
        response = await client.get("/v1/agenda?view=month", headers=auth_headers)
        days = response.json()["data"]["days"]
        assert len(days) % 7 == 0

    async def test_overdue_items_get_their_own_bucket(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """At the bottom of a scrolled-away day, an overdue task is a task
        nobody ever sees again."""
        entry = await _create_task(client, auth_headers)
        past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        await client.post(
            f"/v1/entries/{entry['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": past},
        )

        response = await client.get("/v1/agenda?view=week", headers=auth_headers)
        overdue = response.json()["data"]["overdue"]
        assert any(item["entry"]["id"] == entry["id"] for item in overdue)

    async def test_the_agenda_reports_the_users_timezone(
        self, client: AsyncClient, auth_headers
    ) -> None:
        response = await client.get("/v1/agenda", headers=auth_headers)
        assert response.json()["data"]["timezone"] == "Europe/Paris"

    async def test_unscheduled_items_are_offered_on_request(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _create_task(client, auth_headers, title="Sans échéance")

        response = await client.get(
            "/v1/agenda?view=week&include_unscheduled=true", headers=auth_headers
        )
        titles = [item["entry"]["title"] for item in response.json()["data"]["unscheduled"]]
        assert "Sans échéance" in titles


class TestCalendar:
    async def test_returns_a_cell_per_day(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get("/v1/calendar", headers=auth_headers)
        assert response.status_code == 200
        cells = response.json()["data"]["cells"]
        assert len(cells) % 7 == 0
        assert all("total" in cell for cell in cells)

    async def test_counts_a_task_on_its_day(self, client: AsyncClient, auth_headers) -> None:
        entry = await _create_task(client, auth_headers)
        due = datetime.now(UTC) + timedelta(days=1)
        await client.post(
            f"/v1/entries/{entry['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": due.isoformat()},
        )

        response = await client.get("/v1/calendar", headers=auth_headers)
        cells = response.json()["data"]["cells"]
        assert sum(cell["total"] for cell in cells) >= 1


class TestBulk:
    async def test_applies_one_change_to_many(self, client: AsyncClient, auth_headers) -> None:
        ids = [
            (await _create_task(client, auth_headers, title=f"Tâche {index}"))["id"]
            for index in range(3)
        ]

        response = await client.post(
            "/v1/entries/bulk",
            headers=auth_headers,
            json={"ids": ids, "priority": "high"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["matched"] == 3

        listed = await client.get("/v1/entries?entry_type=task", headers=auth_headers)
        priorities = {item["task"]["priority"] for item in listed.json()["data"]}
        assert priorities == {"high"}

    async def test_ignores_ids_belonging_to_another_tenant(
        self, client: AsyncClient, auth_headers, other_auth_headers
    ) -> None:
        """RLS scopes the read, so the foreign id simply matches nothing — no
        error, no leak, no partial application."""
        mine = await _create_task(client, auth_headers)
        theirs = await _create_task(client, other_auth_headers, title="Chez eux")

        response = await client.post(
            "/v1/entries/bulk",
            headers=auth_headers,
            json={"ids": [mine["id"], theirs["id"]], "priority": "urgent"},
        )

        assert response.json()["data"]["matched"] == 1

        check = await client.get(f"/v1/entries/{theirs['id']}", headers=other_auth_headers)
        assert check.json()["data"]["task"]["priority"] == "normal"

    async def test_refuses_an_oversized_batch(self, client: AsyncClient, auth_headers) -> None:
        import uuid as uuid_module

        response = await client.post(
            "/v1/entries/bulk",
            headers=auth_headers,
            json={"ids": [str(uuid_module.uuid4()) for _ in range(201)], "priority": "low"},
        )
        assert response.status_code == 422


class TestPinning:
    async def test_pin_and_unpin(self, client: AsyncClient, auth_headers) -> None:
        entry = await _create_task(client, auth_headers)

        pinned = await client.post(
            f"/v1/entries/{entry['id']}/pin", headers=auth_headers, json={"pinned": True}
        )
        assert pinned.status_code == 200

        search = await client.get("/v1/search?q=is:pinned", headers=auth_headers)
        assert search.json()["data"]["total"] == 1

        await client.post(
            f"/v1/entries/{entry['id']}/pin", headers=auth_headers, json={"pinned": False}
        )
        search = await client.get("/v1/search?q=is:pinned", headers=auth_headers)
        assert search.json()["data"]["total"] == 0
