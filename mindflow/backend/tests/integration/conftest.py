"""API-level fixtures: a client authenticated as a real, provisioned user."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.deps import reset_verifier
from app.config import Settings
from app.infra.auth.supabase import make_local_token
from app.infra.db.session import dispose_engine, init_engine
from app.main import create_app
from app.workers.pipeline.runner import reset_inline_queue
from tests.conftest import APP_DATABASE_URL, TEST_DATABASE_URL


@pytest_asyncio.fixture
async def api_settings(tmp_path_factory) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(
        env="test",
        database_url=APP_DATABASE_URL,
        # Cross-tenant jobs need a role RLS does not filter (ADR-042). In tests
        # that is the owner connection; in production it is `mindflow_maintenance`.
        maintenance_database_url=TEST_DATABASE_URL,
        storage_backend="local",
        storage_local_root=str(tmp_path_factory.mktemp("objects")),
        stt_backend="fake",
        llm_backend="fake",
        queue_backend="inline",
        # Phase 4 encrypts OAuth tokens at rest, so the test settings
        # need a key like any other deployment.
        token_encryption_keys="test:bWluZGZsb3ctdGVzdC1rZXktMzItYnl0ZXMtISF4eXo=",
        public_base_url="https://test.mindflow.invalid",
        log_format="console",
        log_level="warning",
    )


@pytest_asyncio.fixture
async def client(api_settings: Settings, clean_db) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    reset_verifier()
    reset_inline_queue()
    await dispose_engine()
    init_engine(api_settings)

    app = create_app(api_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http

    await dispose_engine()


@pytest_asyncio.fixture
def auth_headers() -> dict[str, str]:
    """A token for a brand-new user — the account is provisioned lazily on the
    first authenticated call (ADR-029)."""
    subject = f"auth0|{uuid.uuid4()}"
    token = make_local_token(subject, f"{uuid.uuid4()}@example.test")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
def other_auth_headers() -> dict[str, str]:
    subject = f"auth0|{uuid.uuid4()}"
    token = make_local_token(subject, f"{uuid.uuid4()}@example.test")
    return {"Authorization": f"Bearer {token}"}
