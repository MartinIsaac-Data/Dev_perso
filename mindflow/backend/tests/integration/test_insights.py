"""Search, statistics, history, tags and saved filters, end to end.

The search tests exercise the generated `search_vector` column against a real
PostgreSQL with the `french` configuration — none of which has an equivalent in
a substitute engine, and all of which is what makes the feature work.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def _entry(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    title: str,
    entry_type: str = "note",
    body: str | None = None,
    due_expression: str | None = None,
    priority: str = "normal",
) -> dict:
    response = await client.post(
        "/v1/entries",
        headers=headers,
        json={
            "entry_type": entry_type,
            "title": title,
            "priority": priority,
            **({"body": body} if body else {}),
            **({"due_expression": due_expression} if due_expression else {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


class TestFullTextSearch:
    async def test_finds_a_word_in_the_title(self, client: AsyncClient, auth_headers) -> None:
        await _entry(client, auth_headers, title="Rappeler le directeur financier")
        await _entry(client, auth_headers, title="Acheter du café")

        response = await client.get("/v1/search?q=directeur", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert "directeur" in data["hits"][0]["entry"]["title"]

    async def test_finds_a_word_in_the_body(self, client: AsyncClient, auth_headers) -> None:
        await _entry(
            client,
            auth_headers,
            title="Réunion",
            body="Il faut valider le budget de la refonte avant vendredi.",
        )
        response = await client.get("/v1/search?q=refonte", headers=auth_headers)
        assert response.json()["data"]["total"] == 1

    async def test_matches_across_inflections(self, client: AsyncClient, auth_headers) -> None:
        """The `french` text-search configuration stems, so "budgets" finds
        "budget". That is the whole reason for using a tsvector rather than
        `ILIKE`."""
        await _entry(client, auth_headers, title="Préparer les budgets annuels")
        response = await client.get("/v1/search?q=budget", headers=auth_headers)
        assert response.json()["data"]["total"] == 1

    async def test_returns_a_highlighted_snippet(self, client: AsyncClient, auth_headers) -> None:
        await _entry(
            client,
            auth_headers,
            title="Note",
            body="Le budget de la refonte doit être validé cette semaine.",
        )
        response = await client.get("/v1/search?q=refonte", headers=auth_headers)
        snippet = response.json()["data"]["hits"][0]["snippet"]
        assert snippet is not None
        assert "«" in snippet

    async def test_a_malformed_query_does_not_error(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """A search box must not be able to return a 500. `websearch_to_tsquery`
        is chosen over `to_tsquery` precisely because it cannot raise."""
        for query in ["budget & | ! ( )", '"unclosed', "-- ; DROP TABLE entry"]:
            response = await client.get("/v1/search", params={"q": query}, headers=auth_headers)
            assert response.status_code == 200

    async def test_filters_without_text_return_chronological_order(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Ranking a pure filter by relevance would shuffle it for no reason."""
        await _entry(client, auth_headers, title="Ancienne", entry_type="task")
        await _entry(client, auth_headers, title="Récente", entry_type="task")

        response = await client.get("/v1/search?q=is:task", headers=auth_headers)
        titles = [hit["entry"]["title"] for hit in response.json()["data"]["hits"]]
        assert titles == ["Récente", "Ancienne"]

    async def test_combines_text_and_filters(self, client: AsyncClient, auth_headers) -> None:
        await _entry(client, auth_headers, title="Budget refonte", entry_type="task")
        await _entry(client, auth_headers, title="Budget vacances", entry_type="idea")

        response = await client.get("/v1/search?q=budget is:task", headers=auth_headers)

        data = response.json()["data"]
        assert data["total"] == 1
        assert data["hits"][0]["entry"]["title"] == "Budget refonte"

    async def test_echoes_the_parsed_query_and_the_ignored_tokens(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """So the interface can say "p:hgih ignoré" instead of silently
        returning everything."""
        response = await client.get(
            "/v1/search", params={"q": "is:task p:hgih"}, headers=auth_headers
        )
        query = response.json()["data"]["query"]
        assert query["types"] == ["task"]
        assert query["ignored"] == ["p:hgih"]

    async def test_priority_filter(self, client: AsyncClient, auth_headers) -> None:
        await _entry(client, auth_headers, title="Urgente", entry_type="task", priority="urgent")
        await _entry(client, auth_headers, title="Calme", entry_type="task", priority="low")

        response = await client.get("/v1/search?q=p:urgent", headers=auth_headers)
        assert response.json()["data"]["total"] == 1

    async def test_overdue_filter(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers, title="En retard", entry_type="task")
        past = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        await client.post(
            f"/v1/entries/{entry['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": past},
        )

        response = await client.get("/v1/search?q=is:overdue", headers=auth_headers)
        assert response.json()["data"]["total"] == 1

    async def test_search_is_scoped_to_the_caller(
        self, client: AsyncClient, auth_headers, other_auth_headers
    ) -> None:
        await _entry(client, auth_headers, title="Confidentiel refonte")
        response = await client.get("/v1/search?q=refonte", headers=other_auth_headers)
        assert response.json()["data"]["total"] == 0

    async def test_an_empty_query_returns_nothing_rather_than_everything(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _entry(client, auth_headers, title="Quelque chose")
        response = await client.get("/v1/search?q=", headers=auth_headers)
        assert response.json()["data"]["total"] == 0


class TestQuickSearch:
    async def test_returns_results_across_kinds(self, client: AsyncClient, auth_headers) -> None:
        await _entry(client, auth_headers, title="Refonte du site")
        await client.post("/v1/projects", headers=auth_headers, json={"name": "Refonte 2027"})

        response = await client.get("/v1/search/quick?q=refonte", headers=auth_headers)

        data = response.json()["data"]
        assert len(data["entries"]) == 1
        assert len(data["projects"]) == 1

    async def test_ignores_a_query_too_short_to_be_useful(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """On one letter, prefix matching returns everything and helps nobody."""
        await _entry(client, auth_headers, title="Refonte")
        response = await client.get("/v1/search/quick?q=r", headers=auth_headers)
        assert response.json()["data"]["entries"] == []

    async def test_matches_mid_word_but_ranks_prefixes_first(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _entry(client, auth_headers, title="Budget refonte")
        await _entry(client, auth_headers, title="Refonte budget")

        response = await client.get("/v1/search/quick?q=refonte", headers=auth_headers)
        titles = [hit["title"] for hit in response.json()["data"]["entries"]]
        assert titles[0] == "Refonte budget"


class TestStatistics:
    async def test_returns_the_full_shape(self, client: AsyncClient, auth_headers) -> None:
        await _entry(client, auth_headers, title="Une tâche", entry_type="task")

        response = await client.get("/v1/stats?window_days=30", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["window_days"] == 30
        assert len(data["daily"]) == 30
        assert data["entries_created"] >= 1
        assert "streak" in data

    async def test_counts_completions(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers, title="À faire", entry_type="task")
        await client.post(f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers)

        data = (await client.get("/v1/stats", headers=auth_headers)).json()["data"]
        assert data["tasks_completed"] == 1
        assert data["completion_rate"] > 0

    async def test_counts_overdue(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers, title="En retard", entry_type="task")
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        await client.post(
            f"/v1/entries/{entry['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": past},
        )

        data = (await client.get("/v1/stats", headers=auth_headers)).json()["data"]
        assert data["tasks_overdue"] == 1

    async def test_reports_the_unflattering_numbers_too(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """A dashboard that counts only successes teaches nothing."""
        data = (await client.get("/v1/stats", headers=auth_headers)).json()["data"]
        for key in (
            "corrections",
            "correction_rate",
            "captures_without_entries",
            "needs_review",
        ):
            assert key in data

    async def test_breaks_down_by_type(self, client: AsyncClient, auth_headers) -> None:
        await _entry(client, auth_headers, title="T", entry_type="task")
        await _entry(client, auth_headers, title="I", entry_type="idea")

        data = (await client.get("/v1/stats", headers=auth_headers)).json()["data"]
        keys = {item["key"] for item in data["by_type"]}
        assert {"task", "idea"} <= keys

    async def test_is_scoped_to_the_caller(
        self, client: AsyncClient, auth_headers, other_auth_headers
    ) -> None:
        await _entry(client, auth_headers, title="Chez moi", entry_type="task")
        data = (await client.get("/v1/stats", headers=other_auth_headers)).json()["data"]
        assert data["entries_created"] == 0


class TestActivity:
    async def test_records_a_completion(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers, title="À terminer", entry_type="task")
        await client.post(f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers)

        response = await client.get(f"/v1/activity?entry_id={entry['id']}", headers=auth_headers)

        actions = [event["action"] for event in response.json()["data"]]
        assert "completed" in actions

    async def test_keeps_the_label_after_the_subject_is_deleted(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """A history that goes blank when its subject does is not a history."""
        entry = await _entry(client, auth_headers, title="Éphémère", entry_type="task")
        await client.post(f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers)
        await client.delete(f"/v1/entries/{entry['id']}", headers=auth_headers)

        response = await client.get("/v1/activity", headers=auth_headers)
        labels = [event["subject_label"] for event in response.json()["data"]]
        assert "Éphémère" in labels

    async def test_is_scoped_to_the_caller(
        self, client: AsyncClient, auth_headers, other_auth_headers
    ) -> None:
        entry = await _entry(client, auth_headers, title="Privé", entry_type="task")
        await client.post(f"/v1/entries/{entry['id']}/complete-task", headers=auth_headers)

        response = await client.get("/v1/activity", headers=other_auth_headers)
        assert response.json()["data"] == []


class TestTags:
    async def test_attach_list_and_detach(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers, title="Avec tags")

        attached = await client.post(
            f"/v1/entries/{entry['id']}/tags",
            headers=auth_headers,
            json={"labels": ["Finance", "urgent"]},
        )
        assert attached.status_code == 200
        tags = attached.json()["data"]
        assert {tag["normalized"] for tag in tags} == {"finance", "urgent"}

        listed = await client.get("/v1/tags", headers=auth_headers)
        assert len(listed.json()["data"]) == 2

        await client.delete(f"/v1/entries/{entry['id']}/tags/{tags[0]['id']}", headers=auth_headers)
        remaining = await client.get(f"/v1/entries/{entry['id']}", headers=auth_headers)
        assert len(remaining.json()["data"]["tags"]) == 1

    async def test_renaming_onto_an_existing_tag_merges(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """That is what the user means when they are fixing a duplicate — not a
        409 on a unique constraint."""
        first = await _entry(client, auth_headers, title="A")
        second = await _entry(client, auth_headers, title="B")
        await client.post(
            f"/v1/entries/{first['id']}/tags", headers=auth_headers, json={"labels": ["finance"]}
        )
        response = await client.post(
            f"/v1/entries/{second['id']}/tags",
            headers=auth_headers,
            json={"labels": ["financier"]},
        )
        source_id = response.json()["data"][0]["id"]

        merged = await client.patch(
            f"/v1/tags/{source_id}", headers=auth_headers, json={"label": "finance"}
        )

        assert merged.status_code == 200
        assert merged.json()["data"]["normalized"] == "finance"
        listed = await client.get("/v1/tags", headers=auth_headers)
        assert len(listed.json()["data"]) == 1

    async def test_merging_an_entry_that_carries_both_tags_does_not_break(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """The composite primary key would otherwise be violated half-way
        through and leave the merge partially applied."""
        entry = await _entry(client, auth_headers, title="Les deux")
        response = await client.post(
            f"/v1/entries/{entry['id']}/tags",
            headers=auth_headers,
            json={"labels": ["alpha", "beta"]},
        )
        tags = {tag["normalized"]: tag["id"] for tag in response.json()["data"]}

        merged = await client.post(
            f"/v1/tags/{tags['alpha']}/merge",
            headers=auth_headers,
            json={"target_id": tags["beta"]},
        )

        assert merged.status_code == 200
        final = await client.get(f"/v1/entries/{entry['id']}", headers=auth_headers)
        assert final.json()["data"]["tags"] == ["beta"]

    async def test_search_by_tag(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers, title="Taguée")
        await _entry(client, auth_headers, title="Sans tag")
        await client.post(
            f"/v1/entries/{entry['id']}/tags", headers=auth_headers, json={"labels": ["finance"]}
        )

        response = await client.get("/v1/search?q=%23finance", headers=auth_headers)
        assert response.json()["data"]["total"] == 1


class TestSavedFilters:
    async def test_create_list_and_delete(self, client: AsyncClient, auth_headers) -> None:
        created = await client.post(
            "/v1/filters",
            headers=auth_headers,
            json={"name": "Urgent cette semaine", "query": "is:task p:urgent due:semaine"},
        )
        assert created.status_code == 201
        saved = created.json()["data"]

        listed = await client.get("/v1/filters", headers=auth_headers)
        assert len(listed.json()["data"]) == 1

        await client.delete(f"/v1/filters/{saved['id']}", headers=auth_headers)
        assert (await client.get("/v1/filters", headers=auth_headers)).json()["data"] == []

    async def test_refuses_a_filter_that_selects_nothing(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Saving an empty filter creates a shortcut meaning "everything", which
        the user already has."""
        response = await client.post(
            "/v1/filters", headers=auth_headers, json={"name": "Vide", "query": "   "}
        )
        assert response.status_code == 422

    async def test_refuses_a_duplicate_name(self, client: AsyncClient, auth_headers) -> None:
        payload = {"name": "Mes tâches", "query": "is:task"}
        await client.post("/v1/filters", headers=auth_headers, json=payload)
        second = await client.post("/v1/filters", headers=auth_headers, json=payload)
        assert second.status_code == 422

    async def test_stores_the_query_string_verbatim(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """The grammar is the contract: a filter saved today keeps working when
        the parser gains a keyword tomorrow."""
        created = await client.post(
            "/v1/filters",
            headers=auth_headers,
            json={"name": "Retard", "query": "is:task is:overdue"},
        )
        assert created.json()["data"]["query"] == "is:task is:overdue"

    async def test_filters_are_per_user(
        self, client: AsyncClient, auth_headers, other_auth_headers
    ) -> None:
        await client.post(
            "/v1/filters", headers=auth_headers, json={"name": "Privé", "query": "is:task"}
        )
        response = await client.get("/v1/filters", headers=other_auth_headers)
        assert response.json()["data"] == []


class TestProjects:
    async def test_detailed_listing_carries_counts(self, client: AsyncClient, auth_headers) -> None:
        project = (
            await client.post("/v1/projects", headers=auth_headers, json={"name": "Refonte"})
        ).json()["data"]

        entry = await _entry(client, auth_headers, title="Dans le projet", entry_type="task")
        await client.patch(
            f"/v1/entries/{entry['id']}",
            headers=auth_headers,
            json={"project_id": project["id"]},
        )

        response = await client.get("/v1/projects/detailed", headers=auth_headers)
        detail = next(p for p in response.json()["data"] if p["id"] == project["id"])
        assert detail["total_count"] == 1

    async def test_renaming_updates_the_slug(self, client: AsyncClient, auth_headers) -> None:
        """A project renamed "Refonte 2027" whose slug still reads
        `refonte-2026` silently breaks `@refonte-2027` in search."""
        project = (
            await client.post("/v1/projects", headers=auth_headers, json={"name": "Refonte 2026"})
        ).json()["data"]

        response = await client.patch(
            f"/v1/projects/{project['id']}",
            headers=auth_headers,
            json={"name": "Refonte 2027"},
        )

        assert response.json()["data"]["slug"] == "refonte-2027"

    async def test_project_stats(self, client: AsyncClient, auth_headers) -> None:
        project = (
            await client.post("/v1/projects", headers=auth_headers, json={"name": "P"})
        ).json()["data"]
        response = await client.get(f"/v1/projects/{project['id']}/stats", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0
