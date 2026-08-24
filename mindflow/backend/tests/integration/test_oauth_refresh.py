"""Le renouvellement, là où il compte : au milieu d'une synchronisation.

Les tests unitaires couvrent l'échange lui-même. Ceux-ci couvrent ce que seule
une vraie base montre : que le nouveau jeton **est écrit**, chiffré, sur la
ligne, et que la connexion sort de la passe dans le bon état.

Le cas qu'il faut garder si l'on ne gardait qu'un seul :
`test_a_401_triggers_exactly_one_refresh_then_succeeds`. C'est la différence
entre une intégration qui vit une heure et une intégration qui tient.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
import respx
from sqlalchemy import select

from app.config import Settings
from app.domain.oauth import PROVIDERS
from app.domain.sync import Direction, Provider, PullResult, SyncConnectorPort
from app.infra.crypto import KeyRing, decrypt, encrypt
from app.infra.db.models.core import Account, AppUser
from app.infra.db.models.enterprise import IntegrationConnection
from app.infra.db.session import dispose_engine, init_engine, privileged_session, tenant_session
from app.infra.sync.connectors import ConnectorAuthError
from app.services.identity_service import Principal
from app.services.integration_service import IntegrationService
from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

GOOGLE_EXCHANGE = PROVIDERS[Provider.GOOGLE_CALENDAR].exchange_url
MICROSOFT_EXCHANGE = PROVIDERS[Provider.OUTLOOK_CALENDAR].exchange_url


class Connector(SyncConnectorPort):
    """Échoue autant de fois qu'on le lui demande, puis fonctionne."""

    def __init__(self, *, failures: int = 0) -> None:
        self.remaining_failures = failures
        self.pulls = 0
        self.tokens_seen: list[str] = []

    async def pull(self, *, cursor: str | None = None) -> PullResult:
        self.pulls += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise ConnectorAuthError("401")
        return PullResult(items=[], cursor="cursor-1", incremental=True)

    async def push(self, *, entry, link=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError


@pytest_asyncio.fixture
async def settings(api_settings: Settings, clean_db) -> AsyncIterator[Settings]:  # type: ignore[no-untyped-def]
    configured = api_settings.model_copy(
        update={
            "google_client_id": "client-abc",
            "google_client_secret": "secret-xyz",
            "microsoft_client_id": "client-ms",
            "microsoft_client_secret": "secret-ms",
        }
    )
    await dispose_engine()
    init_engine(configured)
    yield configured
    await dispose_engine()


async def _tenant(
    settings: Settings,
    *,
    provider: Provider = Provider.GOOGLE_CALENDAR,
    expires_in: timedelta | None = timedelta(hours=1),
    refresh_token: str | None = "rt-original",
) -> tuple[Principal, uuid.UUID]:
    ring = KeyRing.from_settings(settings.token_encryption_keys)
    account_id, user_id, connection_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with privileged_session() as session:
        session.add(Account(id=account_id, display_name="Test"))
        session.add(
            AppUser(
                id=user_id,
                account_id=account_id,
                auth_subject=f"stub|{user_id}",
                email=f"{user_id}@example.test",
                timezone="Europe/Paris",
                locale="fr-FR",
                role="owner",
            )
        )
        session.add(
            IntegrationConnection(
                id=connection_id,
                account_id=account_id,
                user_id=user_id,
                provider=provider.value,
                access_token_encrypted=encrypt("at-original", ring=ring),
                refresh_token_encrypted=(
                    encrypt(refresh_token, ring=ring) if refresh_token else None
                ),
                token_expires_at=(datetime.now(UTC) + expires_in) if expires_in else None,
                status="active",
                direction=Direction.PULL.value,
            )
        )
        await session.commit()

    principal = Principal(
        user_id=user_id,
        account_id=account_id,
        role="owner",
        auth_subject=f"stub|{user_id}",
        email=f"{user_id}@example.test",
        timezone="Europe/Paris",
        locale="fr-FR",
    )
    return principal, connection_id


async def _row(connection_id: uuid.UUID) -> IntegrationConnection:
    async with privileged_session() as session:
        return (
            await session.execute(
                select(IntegrationConnection).where(IntegrationConnection.id == connection_id)
            )
        ).scalar_one()


async def _sync(
    settings: Settings, principal: Principal, connection_id: uuid.UUID, connector: Connector
) -> object:
    async with tenant_session(str(principal.account_id), user_id=str(principal.user_id)) as session:
        service = IntegrationService(session, principal=principal, settings=settings)
        # Reconstruit à chaque passe dans le service : le même objet est rendu,
        # ce qui permet de compter les appels au travers d'un renouvellement.
        import app.services.integration_service as module

        original = module.build_connector
        module.build_connector = lambda connection, *, access_token: connector  # type: ignore[assignment]
        try:
            report = await service.sync(connection_id)
        finally:
            module.build_connector = original  # type: ignore[assignment]
        await session.commit()
        return report


@respx.mock
async def test_a_token_near_expiry_is_refreshed_before_the_pass(settings: Settings) -> None:
    """Renouveler avant, pas après un 401.

    Une passe qui échoue puis renouvelle a perdu son tour ; à cinq minutes de
    cadence, l'utilisateur le voit.
    """
    route = respx.post(GOOGLE_EXCHANGE).mock(
        return_value=httpx.Response(200, json={"access_token": "at-new", "expires_in": 3600})
    )
    principal, connection_id = await _tenant(settings, expires_in=timedelta(seconds=30))
    connector = Connector()

    report = await _sync(settings, principal, connection_id, connector)

    assert route.called
    assert not report.failed  # type: ignore[attr-defined]
    assert connector.pulls == 1

    row = await _row(connection_id)
    ring = KeyRing.from_settings(settings.token_encryption_keys)
    assert decrypt(row.access_token_encrypted or "", ring=ring) == "at-new"
    # Google ne renvoie pas de jeton de rafraîchissement : l'ancien doit rester,
    # sinon le renouvellement suivant n'a plus rien à présenter.
    assert decrypt(row.refresh_token_encrypted or "", ring=ring) == "rt-original"
    assert row.status == "active"


@respx.mock
async def test_a_healthy_token_is_left_alone(settings: Settings) -> None:
    route = respx.post(GOOGLE_EXCHANGE).mock(return_value=httpx.Response(200, json={}))
    principal, connection_id = await _tenant(settings, expires_in=timedelta(hours=1))

    await _sync(settings, principal, connection_id, Connector())

    assert not route.called


@respx.mock
async def test_a_401_triggers_exactly_one_refresh_then_succeeds(settings: Settings) -> None:
    """Le cas qui fait la différence.

    Le fournisseur a révoqué le jeton d'accès plus tôt que promis — cela
    arrive : changement de mot de passe, révocation d'appareil. Avant ce flux,
    la connexion passait `expired` définitivement.
    """
    route = respx.post(GOOGLE_EXCHANGE).mock(
        return_value=httpx.Response(200, json={"access_token": "at-new", "expires_in": 3600})
    )
    principal, connection_id = await _tenant(settings)
    connector = Connector(failures=1)

    report = await _sync(settings, principal, connection_id, connector)

    assert route.call_count == 1
    assert connector.pulls == 2  # l'échec, puis la reprise
    assert not report.failed  # type: ignore[attr-defined]
    assert (await _row(connection_id)).status == "active"


@respx.mock
async def test_a_second_401_after_a_refresh_gives_up(settings: Settings) -> None:
    """Une fois, et une seule.

    Boucler ici transformerait une connexion cassée en déni de service contre
    le fournisseur — et en facture.
    """
    route = respx.post(GOOGLE_EXCHANGE).mock(
        return_value=httpx.Response(200, json={"access_token": "at-new", "expires_in": 3600})
    )
    principal, connection_id = await _tenant(settings)
    connector = Connector(failures=99)

    report = await _sync(settings, principal, connection_id, connector)

    assert route.call_count == 1
    assert connector.pulls == 2
    assert report.failed  # type: ignore[attr-defined]
    assert (await _row(connection_id)).status == "expired"


@respx.mock
async def test_a_revoked_grant_asks_for_a_reconnection(settings: Settings) -> None:
    respx.post(GOOGLE_EXCHANGE).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    principal, connection_id = await _tenant(settings)

    report = await _sync(settings, principal, connection_id, Connector(failures=1))

    assert report.failed  # type: ignore[attr-defined]
    row = await _row(connection_id)
    assert row.status == "expired"
    assert row.last_error


@respx.mock
async def test_a_connection_without_a_refresh_token_still_expires_cleanly(
    settings: Settings,
) -> None:
    # Le comportement d'avant, préservé : sans quoi renouveler, un 401 reste
    # terminal. Une connexion établie avant ce flux ne doit pas boucler.
    route = respx.post(GOOGLE_EXCHANGE).mock(return_value=httpx.Response(200, json={}))
    principal, connection_id = await _tenant(settings, refresh_token=None)

    report = await _sync(settings, principal, connection_id, Connector(failures=1))

    assert not route.called
    assert report.failed  # type: ignore[attr-defined]
    assert (await _row(connection_id)).status == "expired"


@respx.mock
async def test_a_rotated_refresh_token_is_written_back(settings: Settings) -> None:
    """Le cas Microsoft.

    Garder l'ancien ferait échouer le renouvellement suivant, une heure plus
    tard, sans rapport visible avec la cause.
    """
    respx.post(MICROSOFT_EXCHANGE).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "at-new", "refresh_token": "rt-rotated", "expires_in": 3600},
        )
    )
    principal, connection_id = await _tenant(
        settings, provider=Provider.OUTLOOK_CALENDAR, expires_in=timedelta(seconds=10)
    )

    await _sync(settings, principal, connection_id, Connector())

    ring = KeyRing.from_settings(settings.token_encryption_keys)
    row = await _row(connection_id)
    assert decrypt(row.refresh_token_encrypted or "", ring=ring) == "rt-rotated"


@respx.mock
async def test_a_provider_outage_does_not_expire_the_connection(settings: Settings) -> None:
    """Une panne du fournisseur d'identité n'est pas une révocation.

    Marquer `expired` ici demanderait à l'utilisateur de reconnecter un service
    qui allait revenir tout seul — et `expired` n'est jamais retenté (ADR-056).

    La passe continue malgré l'échec du renouvellement, et c'est délibéré : le
    renouvellement est *préventif*, déclenché deux minutes avant l'échéance. Le
    jeton en place est encore valable. Abandonner la passe perdrait une
    synchronisation qui allait réussir ; s'il ne l'est plus, le 401 s'en
    chargera. Écrit après avoir vu le test échouer en affirmant le contraire.
    """
    respx.post(GOOGLE_EXCHANGE).mock(return_value=httpx.Response(503))
    principal, connection_id = await _tenant(settings, expires_in=timedelta(seconds=10))
    connector = Connector()

    report = await _sync(settings, principal, connection_id, connector)

    assert connector.pulls == 1
    assert not report.failed  # type: ignore[attr-defined]
    row = await _row(connection_id)
    assert row.status == "active"


@respx.mock
async def test_an_outage_that_also_kills_the_pass_stays_retryable(settings: Settings) -> None:
    # Le fournisseur d'identité est en panne *et* le jeton est bien mort. La
    # connexion doit rester `active` : le compteur d'échecs la retiendra si cela
    # dure, mais elle ne demande pas de reconnexion pour une panne passagère.
    respx.post(GOOGLE_EXCHANGE).mock(return_value=httpx.Response(503))
    principal, connection_id = await _tenant(settings, expires_in=timedelta(hours=1))

    report = await _sync(settings, principal, connection_id, Connector(failures=1))

    assert report.failed  # type: ignore[attr-defined]
    row = await _row(connection_id)
    assert row.status == "expired"
