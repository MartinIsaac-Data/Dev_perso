"""Automatic detection of people, products, companies, projects, decisions,
risks and actions — and the resolution that turns detections into a graph.

The extraction half is driven by a scripted chat port: what is under test is not
whether a model finds "Sylvie Mba" in a sentence (it does), but what the service
does with the answer. Two properties carry the feature:

* **Re-extraction replaces.** `test_reextracting_does_not_double_the_counts` is
  the important one. Incrementing `mention_count` is the obvious implementation,
  and one re-index then doubles every number in the product, « quels sujets
  reviennent souvent ? » answers with inflated counts, and nothing looks broken.
* **Resolution is deterministic.** The same person named three ways across three
  months is one row, decided in code — never by asking a model, which would give
  a different answer on a different day.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text

from app.domain.enums import EntryStatus, EntryType
from app.domain.errors import ExtractionUnavailableError
from app.domain.knowledge import EntityKind
from app.domain.ports import AiUsage, ChatChunk, ChatPort, ChatRequest
from app.infra.db.models.ai import Entity, EntityMention
from app.infra.db.models.core import Entry
from app.services.knowledge_service import KnowledgeService
from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


class ScriptedChat(ChatPort):
    """Returns a prepared extraction, so the service is what is under test."""

    name = "scripted"
    supports_json_schema = True

    def __init__(self, payload: dict | str, *, refused: bool = False) -> None:
        self.model = "scripted"
        self._body = payload if isinstance(payload, str) else json.dumps(payload)
        self._refused = refused
        self.calls = 0

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        self.calls += 1
        yield ChatChunk(text=self._body)
        yield ChatChunk(
            done=True,
            usage=AiUsage(model=self.model),
            finish_reason="refusal" if self._refused else "stop",
        )


class UnavailableChat(ChatPort):
    name = "unavailable"

    def __init__(self) -> None:
        self.model = "unavailable"

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        raise ExtractionUnavailableError("down")
        yield ChatChunk()  # pragma: no cover - unreachable, satisfies the generator


def _entity(kind: str, name: str, confidence: float = 0.9, **extra: object) -> dict:
    return {"kind": kind, "name": name, "confidence": confidence, **extra}


def _extraction(*entities: dict, topics: list[str] | None = None) -> dict:
    return {"entities": list(entities), "topics": topics or []}


async def _make_entry(session, account_id, user_id, title: str, body: str | None = None) -> Entry:  # type: ignore[no-untyped-def]
    entry = Entry(
        id=uuid.uuid4(),
        account_id=account_id,
        user_id=user_id,
        entry_type=EntryType.NOTE.value,
        title=title,
        body=body,
        status=EntryStatus.ACTIVE,
        occurred_at=datetime.now(UTC),
    )
    session.add(entry)
    await session.flush()
    return entry


@pytest.fixture
def tenant(two_tenants):  # type: ignore[no-untyped-def]
    return two_tenants[0]


async def _tenant_session(session_factory, account_id):  # type: ignore[no-untyped-def]
    session = session_factory()
    await session.execute(
        text("SELECT set_config('app.account_id', :aid, true)"), {"aid": str(account_id)}
    )
    return session


class TestTheSevenKinds:
    async def test_all_seven_kinds_are_detected_and_stored(self, session_factory, tenant) -> None:
        chat = ScriptedChat(
            _extraction(
                _entity("person", "Sylvie Mba", role="DAF"),
                _entity("product", "Offre Premium"),
                _entity("company", "Total Gabon"),
                _entity("project", "Forecast Gabon"),
                _entity("decision", "Reporter le lancement au 3 mars"),
                _entity("risk", "Rupture de stock au trimestre"),
                _entity("action", "Rappeler le fournisseur"),
                topics=["forecast", "logistique"],
            )
        )
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(
                session, tenant["account_id"], tenant["user_id"], "Comité forecast"
            )
            outcome = await KnowledgeService(session, chat=chat).extract_for_entry(entry)

            assert not outcome.empty
            assert outcome.created == 7
            kinds = {EntityKind(entity.kind) for entity in outcome.entities}
            assert kinds == set(EntityKind)
            assert outcome.topics == ["forecast", "logistique"]

    async def test_a_role_is_kept_on_the_mention_not_the_entity(
        self, session_factory, tenant
    ) -> None:
        # "DAF" is how Sylvie appeared in *this* note. She may appear as
        # something else elsewhere, so the qualifier belongs to the mention.
        chat = ScriptedChat(_extraction(_entity("person", "Sylvie Mba", role="DAF")))
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            await KnowledgeService(session, chat=chat).extract_for_entry(entry)

            mention = (
                await session.execute(
                    select(EntityMention).where(EntityMention.entry_id == entry.id)
                )
            ).scalar_one()
            assert mention.role == "DAF"


class TestResolution:
    async def test_the_same_person_named_three_ways_is_one_entity(
        self, session_factory, tenant
    ) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            service_a = KnowledgeService(
                session, chat=ScriptedChat(_extraction(_entity("person", "Jean-Marc Ondo")))
            )
            service_b = KnowledgeService(
                session, chat=ScriptedChat(_extraction(_entity("person", "jean marc ondo")))
            )
            service_c = KnowledgeService(
                session, chat=ScriptedChat(_extraction(_entity("person", "JEAN-MARC ONDO")))
            )
            for index, service in enumerate((service_a, service_b, service_c)):
                entry = await _make_entry(
                    session, tenant["account_id"], tenant["user_id"], f"Note {index}"
                )
                await service.extract_for_entry(entry)

            total = (
                await session.execute(
                    select(func.count()).select_from(Entity).where(Entity.kind == "person")
                )
            ).scalar_one()
            assert total == 1

            entity = (await session.execute(select(Entity))).scalar_one()
            assert entity.mention_count == 3

    async def test_the_fuller_name_wins(self, session_factory, tenant) -> None:
        # "Sylvie Mba" and "Sylvie" resolve separately (different keys); within
        # one key the richest phrasing survives.
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            first = ScriptedChat(_extraction(_entity("person", "sylvie mba")))
            second = ScriptedChat(_extraction(_entity("person", "Sylvie Mba Nguema")))
            for chat in (first, second):
                entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
                await KnowledgeService(session, chat=chat).extract_for_entry(entry)

            names = {entity.name for entity in (await session.execute(select(Entity))).scalars()}
            assert "Sylvie Mba Nguema" in names

    async def test_the_same_name_under_two_kinds_stays_separate(
        self, session_factory, tenant
    ) -> None:
        chat = ScriptedChat(_extraction(_entity("company", "Orange"), _entity("product", "Orange")))
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            outcome = await KnowledgeService(session, chat=chat).extract_for_entry(entry)
            assert outcome.created == 2

    async def test_low_confidence_detections_are_discarded(self, session_factory, tenant) -> None:
        chat = ScriptedChat(
            _extraction(
                _entity("person", "Peut-être Paul", confidence=0.2),
                _entity("person", "Sylvie", confidence=0.95),
            )
        )
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            outcome = await KnowledgeService(session, chat=chat).extract_for_entry(entry)
            assert [entity.name for entity in outcome.entities] == ["Sylvie"]


class TestIdempotence:
    async def test_reextracting_does_not_double_the_counts(self, session_factory, tenant) -> None:
        # The bug this prevents has no symptom: counts inflate, the recurring
        # topics view looks busier, and nothing errors.
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            chat = ScriptedChat(_extraction(_entity("project", "Forecast Gabon")))
            service = KnowledgeService(session, chat=chat)

            await service.extract_for_entry(entry)
            await service.extract_for_entry(entry)
            await service.extract_for_entry(entry)

            entity = (await session.execute(select(Entity))).scalar_one()
            assert entity.mention_count == 1

    async def test_an_entity_no_longer_named_stops_being_counted(
        self, session_factory, tenant
    ) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            await KnowledgeService(
                session, chat=ScriptedChat(_extraction(_entity("person", "Paul")))
            ).extract_for_entry(entry)
            await KnowledgeService(
                session, chat=ScriptedChat(_extraction(_entity("person", "Sylvie")))
            ).extract_for_entry(entry)

            paul = (await session.execute(select(Entity).where(Entity.name == "Paul"))).scalar_one()
            assert paul.mention_count == 0


class TestDegradation:
    async def test_an_empty_extraction_is_a_normal_result(self, session_factory, tenant) -> None:
        # Most captures name nothing. Treating that as failure would have the
        # worker retrying half the corpus forever.
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            outcome = await KnowledgeService(
                session, chat=ScriptedChat(_extraction())
            ).extract_for_entry(entry)
            assert outcome.empty

    async def test_malformed_output_does_not_raise(self, session_factory, tenant) -> None:
        # Unlike note extraction, where a schema violation fails the capture, a
        # bad entity extraction is survivable: the entry exists and is
        # searchable, it just contributes nothing to the graph this pass.
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            outcome = await KnowledgeService(
                session, chat=ScriptedChat("pas du tout du JSON")
            ).extract_for_entry(entry)
            assert outcome.empty

    async def test_a_refusal_is_not_an_error(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            outcome = await KnowledgeService(
                session, chat=ScriptedChat(_extraction(), refused=True)
            ).extract_for_entry(entry)
            assert outcome.empty

    async def test_a_provider_outage_propagates_so_the_worker_retries(
        self, session_factory, tenant
    ) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            with pytest.raises(ExtractionUnavailableError):
                await KnowledgeService(session, chat=UnavailableChat()).extract_for_entry(entry)


class TestRecurringThemes:
    async def test_ranks_by_how_often_something_is_named(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            for index in range(3):
                entry = await _make_entry(
                    session, tenant["account_id"], tenant["user_id"], f"Note {index}"
                )
                await KnowledgeService(
                    session,
                    chat=ScriptedChat(
                        _extraction(
                            _entity("project", "Forecast Gabon"),
                            *([_entity("person", "Sylvie")] if index < 2 else []),
                        )
                    ),
                ).extract_for_entry(entry)

            themes = await KnowledgeService(session).recurring_themes()

            assert [theme.name for theme in themes] == ["Forecast Gabon", "Sylvie"]
            assert themes[0].count == 3

    async def test_something_named_once_is_not_recurring(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _make_entry(session, tenant["account_id"], tenant["user_id"], "Note")
            await KnowledgeService(
                session, chat=ScriptedChat(_extraction(_entity("person", "Paul")))
            ).extract_for_entry(entry)

            assert await KnowledgeService(session).recurring_themes() == []

    async def test_themes_can_be_narrowed_to_a_kind(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            for index in range(2):
                entry = await _make_entry(
                    session, tenant["account_id"], tenant["user_id"], f"Note {index}"
                )
                await KnowledgeService(
                    session,
                    chat=ScriptedChat(
                        _extraction(_entity("risk", "Rupture de stock"), _entity("person", "Paul"))
                    ),
                ).extract_for_entry(entry)

            risks = await KnowledgeService(session).recurring_themes(kinds=(EntityKind.RISK,))

            assert [theme.name for theme in risks] == ["Rupture de stock"]
