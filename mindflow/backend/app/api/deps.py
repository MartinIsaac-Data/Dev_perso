"""FastAPI dependencies.

The request chain of Architecture.md §7.2, expressed as dependencies:
correlation → authentication → tenant context → handler. The tenant context is
posted before the handler runs, so no handler can forget it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.domain.errors import AuthError
from app.domain.ports import AnalyzerPort, ObjectStoragePort, TaskQueuePort, TranscriberPort
from app.infra.auth.supabase import TokenVerifier
from app.infra.db.session import set_tenant_context, tenant_session
from app.observability.logging import account_id_var
from app.services.identity_service import IdentityService, Principal

bearer_scheme = HTTPBearer(auto_error=False, description="Jeton d'accès Supabase")


def settings_dep(request: Request) -> Settings:
    """Read the settings the app was actually built with.

    Reading the global singleton here instead would make `create_app(settings)`
    silently inert: the app object would carry one configuration while every
    dependency used another. That is how a test ends up talking to production
    Redis, and how a staging deploy ends up on the wrong storage backend.
    """
    settings: Settings | None = getattr(request.app.state, "settings", None)
    return settings or get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]


# Explicit singleton rather than lru_cache: Settings is a pydantic model and is
# not hashable, and the verifier holds the JWKS key cache — rebuilding it per
# request would refetch keys on every call.
_verifier_instance: TokenVerifier | None = None


def _verifier(settings: Settings) -> TokenVerifier:
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = TokenVerifier(settings)
    return _verifier_instance


def reset_verifier() -> None:
    """Test hook — settings change between test cases."""
    global _verifier_instance
    _verifier_instance = None


async def get_principal(
    request: Request,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    """Verify the token and resolve (or provision) the MindFlow principal.

    The lookup runs under the narrow `app_user_self_lookup` policy of migration
    0004 — not a privileged connection. Authentication does not weaken RLS.
    """
    if credentials is None or not credentials.credentials:
        raise AuthError("En-tête Authorization manquant ou mal formé.")

    claims = _verifier(settings).verify(credentials.credentials)

    async with tenant_session(None, auth_subject=claims.subject) as session:
        principal = await IdentityService(session).resolve(claims)

    account_id_var.set(str(principal.account_id))
    request.state.principal = principal
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


async def get_session(principal: PrincipalDep) -> AsyncIterator[AsyncSession]:
    """A transaction already scoped to the caller's tenant."""
    async with tenant_session(principal.account_id) as session:
        await set_tenant_context(session, auth_subject=principal.auth_subject)
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


# --------------------------------------------------------------------------- #
# Adapters — resolved from configuration so a provider swap is a config change
# (AI.md, I1; ADR-031)
# --------------------------------------------------------------------------- #
def get_storage(settings: SettingsDep) -> ObjectStoragePort:
    from app.infra.storage.factory import build_storage

    return build_storage(settings)


def get_transcriber(settings: SettingsDep) -> TranscriberPort:
    from app.infra.ai.factory import build_transcriber

    return build_transcriber(settings)


def get_analyzer(settings: SettingsDep) -> AnalyzerPort:
    from app.infra.ai.factory import build_analyzer

    return build_analyzer(settings)


async def get_queue(settings: SettingsDep) -> TaskQueuePort:
    """Queue adapter.

    `inline` runs the pipeline in-process (tests, and `docker compose` without a
    worker); `arq` enqueues for a worker to pick up (ADR-006). The orchestrator
    itself never knows which one it is running under.
    """
    if settings.queue_backend == "inline":
        from app.workers.pipeline.runner import inline_queue

        return inline_queue(settings)

    from app.infra.queue.arq_queue import ArqQueue

    return await ArqQueue.connect(settings)


QueueDep = Annotated[TaskQueuePort, Depends(get_queue)]
StorageDep = Annotated[ObjectStoragePort, Depends(get_storage)]
TranscriberDep = Annotated[TranscriberPort, Depends(get_transcriber)]
AnalyzerDep = Annotated[AnalyzerPort, Depends(get_analyzer)]
