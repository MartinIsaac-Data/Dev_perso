"""Indexing and vector retrieval against a real pgvector.

None of this can be tested against a substitute engine: `vector(1536)`, the HNSW
operator class, the `<=>` distance operator and the exclusive-source CHECK are
all PostgreSQL, and all of them are what makes the feature work.

The tests that matter most here are the incremental-reindex ones. Re-embedding
an unchanged chunk is invisible — the search results are identical — and shows
up only on the invoice, months later. `test_reindexing_unchanged_text_touches
_nothing` is the assertion that keeps that honest.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.enums import EntryStatus, EntryType
from app.domain.errors import ExtractionUnavailableError
from app.domain.ports import AiUsage, EmbedderPort, EmbeddingResult
from app.infra.ai.embedders import FakeEmbedder
from app.infra.db.models.ai import Chunk
from app.infra.db.models.core import Entry
from app.services.indexing_service import IndexingService, reset_embeddings
from app.services.retrieval_service import RetrievalService
from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

DIMENSIONS = 1536


class BrokenEmbedder(EmbedderPort):
    """Always unavailable — the provider-outage path."""

    name = "broken"

    def __init__(self) -> None:
        self.model = "broken"
        self.dimensions = DIMENSIONS

    async def embed(self, texts: list[str], *, kind: str = "document") -> EmbeddingResult:
        raise ExtractionUnavailableError("down")


class SteeredEmbedder(EmbedderPort):
    """Returns a chosen vector per text, so distance is under test control.

    A real embedder would make these tests assertions about a model's semantics
    rather than about our SQL, which is not what is being verified here.
    """

    name = "steered"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.model = "steered"
        self.dimensions = DIMENSIONS
        self._vectors = vectors

    async def embed(self, texts: list[str], *, kind: str = "document") -> EmbeddingResult:
        return EmbeddingResult(
            vectors=tuple(tuple(self._vectors.get(t, _axis(0))) for t in texts),
            model=self.model,
            dimensions=self.dimensions,
            usage=AiUsage(model=self.model),
        )


def _axis(index: int) -> list[float]:
    """A unit vector along one axis — orthogonal to every other axis, so cosine
    distance between two of them is exactly 1."""
    vector = [0.0] * DIMENSIONS
    vector[index] = 1.0
    return vector


async def _entry(session, account_id: uuid.UUID, user_id: uuid.UUID, **kwargs) -> Entry:  # type: ignore[no-untyped-def]
    entry = Entry(
        id=uuid.uuid4(),
        account_id=account_id,
        user_id=user_id,
        entry_type=kwargs.pop("entry_type", EntryType.NOTE.value),
        title=kwargs.pop("title", "Titre"),
        body=kwargs.pop("body", None),
        status=EntryStatus.ACTIVE,
        occurred_at=kwargs.pop("occurred_at", datetime.now(UTC)),
        **kwargs,
    )
    session.add(entry)
    await session.flush()
    return entry


@pytest.fixture
def tenant(two_tenants):  # type: ignore[no-untyped-def]
    return two_tenants[0]


async def _tenant_session(session_factory, account_id: uuid.UUID):  # type: ignore[no-untyped-def]
    session = session_factory()
    await session.execute(
        text("SELECT set_config('app.account_id', :aid, true)"), {"aid": str(account_id)}
    )
    return session


class TestChunkWriting:
    async def test_an_entry_becomes_one_chunk(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(
                session,
                tenant["account_id"],
                tenant["user_id"],
                title="Forecast Gabon",
                body="Trois hypothèses de volume pour le trimestre.",
            )
            result = await IndexingService(session).index_entry(entry)

            assert result.created == 1
            chunk = (
                await session.execute(select(Chunk).where(Chunk.entry_id == entry.id))
            ).scalar_one()
            # The title is repeated into the text: a body fragment with no title
            # embeds as an anonymous paragraph and retrieves like one.
            assert "Forecast Gabon" in chunk.text
            assert chunk.embedding is None

    async def test_a_long_entry_becomes_several_chunks(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            body = " ".join(
                f"Le point numéro {i} a été discuté longuement avec toute l'équipe."
                for i in range(80)
            )
            entry = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="Réunion", body=body
            )
            result = await IndexingService(session).index_entry(entry)
            assert result.created > 1

    async def test_reindexing_unchanged_text_touches_nothing(self, session_factory, tenant) -> None:
        # The test that protects the bill. Re-embedding unchanged text is
        # invisible in the results and visible only on the invoice.
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="Stable", body="Inchangé."
            )
            service = IndexingService(session)
            first = await service.index_entry(entry)
            second = await service.index_entry(entry)

            assert first.created == 1
            assert second.created == 0
            assert second.unchanged == 1
            assert second.removed == 0

    async def test_an_edit_replaces_only_what_changed(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="Avant", body="Corps."
            )
            service = IndexingService(session)
            await service.index_entry(entry)

            entry.title = "Après"
            await session.flush()
            result = await service.index_entry(entry)

            assert result.removed == 1
            assert result.created == 1

    async def test_an_embedding_survives_an_unrelated_reindex(
        self, session_factory, tenant
    ) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="Stable", body="Inchangé."
            )
            service = IndexingService(session, embedder=FakeEmbedder(dimensions=DIMENSIONS))
            await service.index_entry(entry)
            await service.embed_pending()

            await service.index_entry(entry)

            chunk = (
                await session.execute(select(Chunk).where(Chunk.entry_id == entry.id))
            ).scalar_one()
            # The row survived, and so did the vector we paid for.
            assert chunk.embedding is not None
            assert chunk.embedded_at is not None

    async def test_a_chunk_cannot_belong_to_two_sources(self, session_factory, tenant) -> None:
        # Enforced by the database, not by the application: "which rows does
        # deleting a capture remove?" must be answerable without reading code.
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            session.add(
                Chunk(
                    account_id=tenant["account_id"],
                    entry_id=None,
                    capture_id=None,
                    chunk_index=0,
                    text="orpheline",
                    content_hash="x" * 32,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()

    async def test_removing_an_entry_drops_its_chunks(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="À supprimer"
            )
            service = IndexingService(session)
            await service.index_entry(entry)

            removed = await service.remove_for_entry(entry.id)

            assert removed == 1
            remaining = (
                await session.execute(
                    select(func.count()).select_from(Chunk).where(Chunk.entry_id == entry.id)
                )
            ).scalar_one()
            assert remaining == 0


class TestEmbedding:
    async def test_pending_chunks_are_embedded(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="À vectoriser"
            )
            service = IndexingService(session, embedder=FakeEmbedder(dimensions=DIMENSIONS))
            await service.index_entry(entry)

            result = await service.embed_pending()

            assert result.embedded == 1
            assert result.remaining == 0
            chunk = (
                await session.execute(select(Chunk).where(Chunk.entry_id == entry.id))
            ).scalar_one()
            assert len(chunk.embedding) == DIMENSIONS
            assert chunk.embedding_model == "fake-embed"

    async def test_a_provider_outage_leaves_the_work_in_the_backlog(
        self, session_factory, tenant
    ) -> None:
        # No "failed" state on purpose: a failed state needs a reset path and
        # somebody to remember it exists.
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(session, tenant["account_id"], tenant["user_id"], title="Note")
            service = IndexingService(session, embedder=BrokenEmbedder())
            await service.index_entry(entry)

            result = await service.embed_pending()

            assert result.embedded == 0
            assert result.failed == 1
            assert result.remaining == 1

    async def test_an_empty_backlog_is_not_an_error(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            service = IndexingService(session, embedder=FakeEmbedder(dimensions=DIMENSIONS))
            assert (await service.embed_pending()).embedded == 0

    async def test_changing_model_clears_the_old_vectors(self, session_factory, tenant) -> None:
        # Two models' vectors occupy different spaces; a corpus half-embedded by
        # each ranks by nothing at all — worse than an empty index, because it
        # looks like it works (ADR-045).
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(session, tenant["account_id"], tenant["user_id"], title="Note")
            service = IndexingService(session, embedder=FakeEmbedder(dimensions=DIMENSIONS))
            await service.index_entry(entry)
            await service.embed_pending()

            cleared = await reset_embeddings(session, model="autre-modele")

            assert cleared == 1
            assert (await service.backlog()) == 1


class TestVectorRetrieval:
    async def test_the_nearest_vector_wins(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            near = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="Proche du sujet"
            )
            far = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="Totalement autre"
            )
            embedder = SteeredEmbedder({"Proche du sujet": _axis(0), "Totalement autre": _axis(1)})
            service = IndexingService(session, embedder=embedder)
            await service.index_entry(near)
            await service.index_entry(far)
            await service.embed_pending()

            retrieval = RetrievalService(session, embedding_model="steered")
            # A query on axis 0: cosine distance 0 to `near`, 1 to `far`.
            result = await retrieval.search("aucun mot commun ici", query_vector=_axis(0))

            assert result.semantic_count >= 1
            assert result.passages[0].title == "Proche du sujet"

    async def test_semantic_search_ignores_another_models_vectors(
        self, session_factory, tenant
    ) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(session, tenant["account_id"], tenant["user_id"], title="Note")
            service = IndexingService(session, embedder=FakeEmbedder(dimensions=DIMENSIONS))
            await service.index_entry(entry)
            await service.embed_pending()

            retrieval = RetrievalService(session, embedding_model="un-autre-modele")
            result = await retrieval.search("zzzz", query_vector=_axis(0))

            # Filtering means a provider migration degrades recall rather than
            # corrupting the ranking with incomparable vectors.
            assert result.semantic_count == 0

    async def test_lexical_and_semantic_agreement_is_marked(self, session_factory, tenant) -> None:
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(
                session,
                tenant["account_id"],
                tenant["user_id"],
                title="Logistique portuaire",
                body="Le port de Libreville est saturé.",
            )
            embedder = SteeredEmbedder({})
            service = IndexingService(session, embedder=embedder)
            await service.index_entry(entry)
            await service.embed_pending()

            retrieval = RetrievalService(session, embedding_model="steered")
            result = await retrieval.search("logistique portuaire", query_vector=_axis(0))

            found = result.passages[0].found_by
            assert "lexical" in [item.value for item in found]
            assert "semantic" in [item.value for item in found]

    async def test_an_unembedded_corpus_still_answers_lexically(
        self, session_factory, tenant
    ) -> None:
        # The state of every deployment before the first worker tick. Normal,
        # not degraded — and it must not be reported as a failure.
        session = await _tenant_session(session_factory, tenant["account_id"])
        async with session:
            entry = await _entry(
                session, tenant["account_id"], tenant["user_id"], title="Logistique portuaire"
            )
            await IndexingService(session).index_entry(entry)

            retrieval = RetrievalService(session, embedding_model="fake-embed")
            result = await retrieval.search("logistique", query_vector=_axis(0))

            assert result.lexical_count == 1
            assert result.semantic_count == 0
            assert result.passages
