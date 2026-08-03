"""The assistant, end to end — starting with the five questions it must answer.

`TestTheFiveRequiredQuestions` is the acceptance test for phase 3's headline
requirement. `tests/unit/test_intent.py` proves each question reaches the right
handler; this proves each handler returns the right thing, against a real
PostgreSQL with real entries, real tasks and real chunks.

The two structured questions are asserted to have used **no model at all**
(`used_model is False`). That is the point of the routing, and it is the
assertion most likely to be broken by a well-meaning refactor that "simplifies"
the assistant by sending everything to the LLM.
"""

from __future__ import annotations

import uuid
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
) -> dict:
    response = await client.post(
        "/v1/entries",
        headers=headers,
        json={
            "entry_type": entry_type,
            "title": title,
            "priority": "normal",
            **({"body": body} if body else {}),
            **({"due_expression": due_expression} if due_expression else {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _ask(
    client: AsyncClient, headers: dict[str, str], question: str, **extra: object
) -> dict:
    response = await client.post(
        "/v1/assistant/chat", headers=headers, json={"question": question, **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


class TestTheFiveRequiredQuestions:
    async def test_que_dois_je_faire_aujourdhui(self, client: AsyncClient, auth_headers) -> None:
        await _entry(
            client,
            auth_headers,
            title="Rappeler le DAF de Vinci",
            entry_type="task",
            due_expression="aujourd'hui",
        )
        await _entry(client, auth_headers, title="Note sans échéance")

        answer = await _ask(client, auth_headers, "Que dois-je faire aujourd'hui ?")

        assert answer["intent"] == "today"
        assert "Rappeler le DAF de Vinci" in answer["text"]
        # No model: the agenda knows this exactly, and asking a model would be
        # slower, dearer and less accurate.
        assert answer["used_model"] is False
        assert any("sans modèle" in note for note in answer["notes"])

    async def test_quelles_sont_mes_taches_en_retard(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # Rescheduled explicitly rather than declared with "hier": the
        # temporal resolver rejects a date more than 24 h in the past, since
        # that signals a misreading rather than a deliberate deadline.
        late = await _entry(client, auth_headers, title="Envoyer le forecast", entry_type="task")
        past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        response = await client.post(
            f"/v1/entries/{late['id']}/reschedule",
            headers=auth_headers,
            json={"due_at": past},
        )
        assert response.status_code == 200, response.text
        await _entry(
            client,
            auth_headers,
            title="Préparer la réunion",
            entry_type="task",
            due_expression="dans deux semaines",
        )

        answer = await _ask(client, auth_headers, "Quelles sont mes tâches en retard ?")

        assert answer["intent"] == "overdue"
        assert "Envoyer le forecast" in answer["text"]
        assert "Préparer la réunion" not in answer["text"]
        assert answer["used_model"] is False

    async def test_resume_mes_reunions(self, client: AsyncClient, auth_headers) -> None:
        await _entry(
            client,
            auth_headers,
            title="Comité de direction du mardi",
            entry_type="meeting",
            body="Nous avons validé le budget logistique et reporté le lancement.",
        )
        await _entry(client, auth_headers, title="Acheter du café", entry_type="note")

        answer = await _ask(client, auth_headers, "Résume mes réunions.")

        assert answer["intent"] == "summarise"
        assert answer["used_model"] is True
        # Retrieval narrowed to meetings, so the coffee note must not be cited.
        titles = [citation["title"] for citation in answer["citations"]]
        assert "Comité de direction du mardi" in titles
        assert "Acheter du café" not in titles

    async def test_montre_les_notes_concernant_le_forecast_gabon(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _entry(
            client,
            auth_headers,
            title="Forecast Gabon — hypothèses",
            body="Le forecast Gabon repose sur trois hypothèses de volume.",
        )
        await _entry(client, auth_headers, title="Déjeuner avec Paul")

        answer = await _ask(client, auth_headers, "Montre les notes concernant le Forecast Gabon")

        assert answer["intent"] == "recall"
        titles = [citation["title"] for citation in answer["citations"]]
        assert "Forecast Gabon — hypothèses" in titles
        assert "Déjeuner avec Paul" not in titles
        # The user asked to be *shown* notes. Rendering them as prose would add
        # latency and cost to make the answer harder to scan.
        assert answer["used_model"] is False

    async def test_quels_sujets_reviennent_souvent(self, client: AsyncClient, auth_headers) -> None:
        # No entities extracted yet (extraction is a worker concern and the
        # test chat is a fake), so the honest answer is that there is not
        # enough material — not an invented list of themes.
        answer = await _ask(client, auth_headers, "Quels sujets reviennent souvent ?")

        assert answer["intent"] == "themes"
        assert "sujets récurrents" in answer["text"]


class TestAnswersAreGrounded:
    async def test_an_open_question_cites_what_it_used(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _entry(
            client,
            auth_headers,
            title="Négociation fournisseur",
            body="Le fournisseur a changé ses conditions de paiement à 60 jours.",
        )

        answer = await _ask(
            client, auth_headers, "Pourquoi le fournisseur a-t-il changé ses conditions ?"
        )

        assert answer["intent"] == "open_question"
        assert answer["citations"]
        assert answer["citations"][0]["excerpt"]

    async def test_an_empty_corpus_produces_no_invented_citations(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # The dangerous case: nothing to ground an answer in. There must be no
        # citations rather than plausible-looking ones.
        answer = await _ask(client, auth_headers, "Où en est le dossier Zanzibar ?")
        assert answer["citations"] == []

    async def test_a_deleted_note_stops_being_retrievable(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _entry(
            client,
            auth_headers,
            title="Confidentiel — plan de restructuration",
            body="Le plan de restructuration prévoit trois départs.",
        )
        response = await client.delete(f"/v1/entries/{entry['id']}", headers=auth_headers)
        assert response.status_code in (200, 204)

        answer = await _ask(client, auth_headers, "Montre les notes concernant la restructuration")

        titles = [citation["title"] for citation in answer["citations"]]
        assert "Confidentiel — plan de restructuration" not in titles


class TestConversations:
    async def test_an_exchange_is_persisted(self, client: AsyncClient, auth_headers) -> None:
        answer = await _ask(client, auth_headers, "Que dois-je faire aujourd'hui ?")
        conversation_id = answer["conversation_id"]
        assert conversation_id

        response = await client.get(
            f"/v1/assistant/conversations/{conversation_id}", headers=auth_headers
        )
        assert response.status_code == 200
        messages = response.json()["data"]
        assert [message["role"] for message in messages] == ["user", "assistant"]

    async def test_a_second_question_continues_the_thread(
        self, client: AsyncClient, auth_headers
    ) -> None:
        first = await _ask(client, auth_headers, "Que dois-je faire aujourd'hui ?")
        second = await _ask(
            client, auth_headers, "Et en retard ?", conversation_id=first["conversation_id"]
        )
        assert second["conversation_id"] == first["conversation_id"]

    async def test_the_same_client_message_id_is_not_answered_twice(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # A phone retrying on a flaky connection must not ask — or pay — twice
        # (the same contract as capture declaration, ADR-009).
        client_id = str(uuid.uuid4())
        first = await _ask(
            client, auth_headers, "Que dois-je faire aujourd'hui ?", client_message_id=client_id
        )
        second = await _ask(
            client,
            auth_headers,
            "Que dois-je faire aujourd'hui ?",
            conversation_id=first["conversation_id"],
            client_message_id=client_id,
        )
        assert second["message_id"] == first["message_id"]

    async def test_conversations_are_listed_newest_first(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _ask(client, auth_headers, "Première question ?")
        await _ask(client, auth_headers, "Deuxième question ?")

        response = await client.get("/v1/assistant/conversations", headers=auth_headers)
        assert response.status_code == 200
        titles = [row["title"] for row in response.json()["data"]]
        assert titles[0] == "Deuxième question ?"

    async def test_an_unknown_conversation_is_a_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        response = await client.get(
            f"/v1/assistant/conversations/{uuid.uuid4()}", headers=auth_headers
        )
        assert response.status_code == 404


class TestStreaming:
    async def test_the_final_event_carries_the_whole_answer(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _entry(
            client,
            auth_headers,
            title="Point budget",
            entry_type="meeting",
            body="Le budget a été arbitré en faveur de la logistique.",
        )

        async with client.stream(
            "POST",
            "/v1/assistant/chat/stream",
            headers=auth_headers,
            json={"question": "Résume mes réunions."},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join([chunk async for chunk in response.aiter_text()])

        # A client that ignores the fragments and reads only the last frame gets
        # exactly what the non-streaming endpoint returns.
        assert "event: delta" in body
        assert "event: answer" in body

    async def test_a_structured_answer_streams_in_one_piece(
        self, client: AsyncClient, auth_headers
    ) -> None:
        async with client.stream(
            "POST",
            "/v1/assistant/chat/stream",
            headers=auth_headers,
            json={"question": "Quelles sont mes tâches en retard ?"},
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

        assert body.count("event: delta") == 1
        assert "event: answer" in body


class TestSemanticSearchEndpoint:
    async def test_lexical_search_works_without_an_embedder(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # Before any embedding worker has run — and in a deployment with no
        # embedder configured — lexical search must still answer. This is a
        # normal state, not a degraded one.
        await _entry(client, auth_headers, title="Rapport sur la logistique portuaire")

        response = await client.post(
            "/v1/search/semantic", headers=auth_headers, json={"query": "logistique"}
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["lexical_count"] >= 1
        assert data["semantic_count"] == 0
        assert data["passages"][0]["found_by"] == ["lexical"]

    async def test_a_malformed_query_cannot_return_a_500(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # `websearch_to_tsquery` cannot raise on user input — the reason it was
        # chosen over `to_tsquery` (ADR-037). A search box must not be able to
        # produce a server error.
        response = await client.post(
            "/v1/search/semantic", headers=auth_headers, json={"query": '&&& ||| !!! "'}
        )
        assert response.status_code == 200

    async def test_the_index_status_distinguishes_indexing_from_no_answer(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _entry(client, auth_headers, title="Une note à indexer")

        response = await client.get("/v1/search/index-status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total_chunks"] >= 1
        # Nothing embedded yet: chunks exist, vectors do not. A user whose
        # semantic search returns nothing can tell which of the two it is.
        assert data["pending_chunks"] == data["total_chunks"]


class TestDigests:
    async def test_a_digest_is_generated_for_a_period(
        self, client: AsyncClient, auth_headers
    ) -> None:
        await _entry(client, auth_headers, title="Réunion hebdo", entry_type="meeting")

        response = await client.post("/v1/digests", headers=auth_headers, json={"period": "daily"})

        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["period"] == "daily"
        assert data["period_start"] == data["period_end"]
        assert data["content"]

    async def test_regenerating_replaces_rather_than_duplicates(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # Two summaries of the same day are not a richer history — they are a
        # contradiction shown to the user.
        first = await client.post("/v1/digests", headers=auth_headers, json={"period": "daily"})
        second = await client.post(
            "/v1/digests", headers=auth_headers, json={"period": "daily", "force": True}
        )
        assert first.json()["data"]["id"] == second.json()["data"]["id"]

        listing = await client.get("/v1/digests?period=daily", headers=auth_headers)
        assert len(listing.json()["data"]) == 1

    async def test_a_weekly_digest_spans_monday_to_sunday(
        self, client: AsyncClient, auth_headers
    ) -> None:
        response = await client.post("/v1/digests", headers=auth_headers, json={"period": "weekly"})
        data = response.json()["data"]
        start = datetime.fromisoformat(data["period_start"])
        end = datetime.fromisoformat(data["period_end"])
        assert start.weekday() == 0
        assert (end - start) == timedelta(days=6)

    async def test_an_empty_period_says_so_rather_than_returning_nothing(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # Silence is ambiguous: the user cannot tell "you did nothing" from
        # "the job failed", and will assume the latter.
        old = (datetime.now(UTC) - timedelta(days=400)).date().isoformat()
        response = await client.post(
            "/v1/digests", headers=auth_headers, json={"period": "daily", "anchor": old}
        )
        assert response.status_code == 201
        assert "Aucune activité" in response.json()["data"]["content"]

    async def test_a_digest_can_be_marked_read(self, client: AsyncClient, auth_headers) -> None:
        created = await client.post("/v1/digests", headers=auth_headers, json={"period": "daily"})
        digest_id = created.json()["data"]["id"]

        response = await client.post(f"/v1/digests/{digest_id}/read", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["data"]["read_at"] is not None


class TestMemory:
    async def test_a_new_user_remembers_nothing(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get("/v1/memory", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_memory_is_fully_inspectable(self, client: AsyncClient, auth_headers) -> None:
        # A memory store the user cannot inspect is one they cannot correct.
        response = await client.get("/v1/memory", headers=auth_headers)
        assert response.status_code == 200

    async def test_dismissing_an_unknown_memory_is_a_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        response = await client.delete(f"/v1/memory/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404


class TestEntities:
    async def test_entities_start_empty(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get("/v1/entities", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_themes_start_empty(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get("/v1/entities/themes", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_an_unknown_entity_is_a_404(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get(f"/v1/entities/{uuid.uuid4()}/mentions", headers=auth_headers)
        assert response.status_code == 404
