"""Driving synchronisation with the seven external services.

The service holds the two things the domain deliberately left out: **where the
tokens live**, and **what to do when a provider misbehaves for a week**.

Three rules it enforces:

**A token is decrypted in exactly one place.** Here. `build_connector` takes the
plaintext as an argument rather than a key ring, so an audit of "who can read
OAuth tokens" is an audit of this file.

**A failing connection stops being retried, and says so.** Six consecutive
failures marks it `error` and the scheduler skips it. Retrying a revoked grant
forever is how integrations generate support load and provider rate-limit bans,
and the user is never told why nothing is syncing.

**Idempotency is enforced by a row, not by hope.** Every external object we have
seen is in `external_link`. A pull that runs twice finds the link and updates;
it does not create a second copy of somebody's meeting.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.enums import EntryOrigin, EntryStatus, EntryType
from app.domain.errors import NotFoundError, ValidationError
from app.domain.oauth import (
    OAuthError,
    make_pkce_pair,
    needs_refresh,
    provider_config,
    supports_oauth,
)
from app.domain.permissions import Action
from app.domain.sync import (
    MAX_CONSECUTIVE_FAILURES,
    Direction,
    Provider,
    RemoteItem,
    Resolution,
    resolve,
)
from app.infra.crypto import KeyRing, decrypt, encrypt
from app.infra.db.models.core import Entry, Task
from app.infra.db.models.enterprise import ExternalLink, IntegrationConnection
from app.infra.oauth import (
    OAuthClient,
    credentials_for,
    decode_state,
    encode_state,
    redirect_uri_for,
)
from app.infra.sync.connectors import ConnectorAuthError, ConnectorUnavailableError
from app.infra.sync.factory import build_connector
from app.observability import metrics
from app.observability.logging import get_logger
from app.services.identity_service import Principal
from app.services.workspace_service import WorkspaceService

log = get_logger("integration")


@dataclass(frozen=True, slots=True)
class AuthorisationRequest:
    """Où envoyer l'utilisateur, et le `state` qui reviendra avec lui."""

    provider: Provider
    url: str
    state: str


@dataclass(slots=True)
class SyncReport:
    provider: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    conflicts: int = 0
    failed: bool = False
    reason: str = ""

    @property
    def touched(self) -> int:
        return self.created + self.updated + self.deleted


class IntegrationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        settings: Settings,
    ) -> None:
        self._session = session
        self._principal = principal
        self._settings = settings
        self._workspaces = WorkspaceService(session, principal=principal)

    # -- Connections --------------------------------------------------------- #

    async def connect(
        self,
        *,
        provider: Provider,
        access_token: str,
        refresh_token: str | None = None,
        expires_at: datetime | None = None,
        label: str | None = None,
        direction: Direction = Direction.PULL,
        settings: dict[str, object] | None = None,
    ) -> IntegrationConnection:
        """Store an authorised grant.

        Called after the OAuth dance completes. The tokens arrive in plaintext
        and leave encrypted; this is the only place either happens.
        """
        await self._workspaces.require(Action.INTEGRATION_CONNECT)

        if direction is Direction.TWO_WAY and not provider.supports_two_way:
            # Slack and Teams have nothing to read. Accepting the setting would
            # produce a connection that silently syncs nothing.
            raise ValidationError(
                f"{provider.label} est une destination sortante uniquement.",
                field="direction",
            )

        ring = self._ring()
        existing = (
            await self._session.execute(
                select(IntegrationConnection).where(
                    IntegrationConnection.user_id == self._principal.user_id,
                    IntegrationConnection.provider == provider.value,
                )
            )
        ).scalar_one_or_none()

        connection = existing or IntegrationConnection(
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            provider=provider.value,
        )
        connection.access_token_encrypted = encrypt(access_token, ring=ring)
        connection.refresh_token_encrypted = (
            encrypt(refresh_token, ring=ring) if refresh_token else None
        )
        connection.token_expires_at = expires_at
        connection.external_account_label = label
        connection.direction = direction.value
        connection.settings = dict(settings or {})
        connection.status = "active"
        # Reconnecting clears the failure state — that is the whole point of
        # reconnecting, and leaving it set would keep the scheduler skipping it.
        connection.consecutive_failures = 0
        connection.last_error = None

        if existing is None:
            self._session.add(connection)
        await self._session.flush()
        log.info("integration.connected", provider=provider.value)
        return connection

    # -- OAuth ---------------------------------------------------------------- #

    def begin_authorisation(self, provider: Provider) -> AuthorisationRequest:
        """L'adresse vers laquelle envoyer l'utilisateur.

        Rien n'est stocké : le vérificateur PKCE et l'identité du demandeur
        voyagent chiffrés dans le `state` (`app/infra/oauth.py`). Pas de table à
        purger, pas d'état qui survit à un redémarrage.
        """
        config = provider_config(provider)
        credentials = credentials_for(provider, self._settings)
        verifier, challenge = make_pkce_pair()
        state = encode_state(
            ring=self._ring(),
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            provider=provider,
            verifier=verifier,
        )
        client = OAuthClient(
            config, credentials, redirect_uri=redirect_uri_for(provider, self._settings)
        )
        return AuthorisationRequest(
            provider=provider,
            url=client.authorisation_url(state=state, challenge=challenge),
            state=state,
        )

    async def complete_authorisation(
        self,
        *,
        code: str,
        state: str,
        label: str | None = None,
        direction: Direction = Direction.PULL,
        settings: dict[str, object] | None = None,
    ) -> IntegrationConnection:
        """Échange le code contre des jetons, puis enregistre la connexion."""
        payload = decode_state(state, ring=self._ring())

        # Le `state` porte qui a demandé. Sans cette comparaison, un retour
        # valide obtenu par un utilisateur pourrait rattacher un compte externe
        # à la connexion d'un autre — c'est la raison d'être du `state`, pas
        # seulement sa protection contre le rejeu.
        if payload.user_id != self._principal.user_id:
            log.warning("oauth.state_user_mismatch", provider=payload.provider.value)
            raise ValidationError("Demande d'autorisation invalide.", field="state")

        provider = payload.provider
        client = OAuthClient(
            provider_config(provider),
            credentials_for(provider, self._settings),
            redirect_uri=redirect_uri_for(provider, self._settings),
        )
        grant = await client.exchange_code(code=code, verifier=payload.verifier)

        if not grant.refresh_token:
            # Signalé, jamais fatal : la connexion fonctionnera une heure puis
            # demandera une reconnexion. C'est le défaut que tout ce flux
            # existe pour supprimer, et le voir dans les journaux vaut mieux que
            # de le découvrir à la 61e minute.
            log.warning("oauth.no_refresh_token", provider=provider.value)

        return await self.connect(
            provider=provider,
            access_token=grant.access_token,
            refresh_token=grant.refresh_token,
            expires_at=grant.expires_at,
            label=label,
            direction=direction,
            settings=settings,
        )

    async def disconnect(self, connection_id: uuid.UUID) -> IntegrationConnection:
        await self._workspaces.require(Action.INTEGRATION_DISCONNECT)
        connection = await self._connection(connection_id)

        connection.status = "revoked"
        # Tokens are cleared, not merely marked. A revoked connection that still
        # holds a live refresh token is a credential nobody is watching.
        connection.access_token_encrypted = None
        connection.refresh_token_encrypted = None
        await self._session.flush()
        log.info("integration.disconnected", provider=connection.provider)
        return connection

    async def list_connections(self) -> list[IntegrationConnection]:
        return list(
            (
                await self._session.execute(
                    select(IntegrationConnection)
                    .where(IntegrationConnection.user_id == self._principal.user_id)
                    .order_by(IntegrationConnection.provider)
                )
            ).scalars()
        )

    # -- Synchronisation ------------------------------------------------------ #

    async def sync(self, connection_id: uuid.UUID) -> SyncReport:
        """Run one synchronisation pass. Never raises for provider trouble."""
        connection = await self._connection(connection_id)
        provider = Provider(connection.provider)
        report = SyncReport(provider=provider.value)

        if not provider.is_server_side:
            # Obsidian is a folder on somebody's disk. Saying so beats a
            # spinner that never resolves.
            report.failed = True
            report.reason = "Synchronisation côté client uniquement."
            return report

        if connection.status != "active":
            report.failed = True
            report.reason = f"Connexion {connection.status}."
            return report

        # Renouvelé *avant* d'essayer plutôt qu'après un 401 : une passe qui
        # échoue puis renouvelle a perdu son tour, et à cinq minutes de cadence
        # cela se voit.
        if needs_refresh(connection.token_expires_at):
            await self._refresh(connection)
            if connection.status != "active":
                report.failed = True
                report.reason = "Reconnexion requise."
                await self._session.flush()
                metrics.integration_syncs_total.labels(provider.value, "failed").inc()
                return report

        try:
            await self._run_pass(connection, report)
            connection.last_sync_at = datetime.now(UTC)
            connection.consecutive_failures = 0
            connection.last_error = None
        except ConnectorAuthError as exc:
            # Un 401 n'est plus terminal en soi : il peut vouloir dire « ce
            # jeton d'accès a été révoqué » comme « il a expiré plus tôt que
            # promis ». On tente le renouvellement une fois, et une seule — une
            # boucle ici deviendrait un déni de service contre le fournisseur.
            refreshed = await self._refresh(connection)
            if refreshed:
                try:
                    await self._run_pass(connection, report)
                    connection.last_sync_at = datetime.now(UTC)
                    connection.consecutive_failures = 0
                    connection.last_error = None
                except ConnectorAuthError as retry_exc:
                    self._mark_expired(connection, retry_exc, report)
                except ConnectorUnavailableError as retry_exc:
                    self._mark_unavailable(connection, retry_exc, report)
            else:
                # Le renouvellement a échoué, ou il n'y avait rien à renouveler.
                # Réessayer un octroi révoqué ne réussit jamais : la connexion
                # est marquée pour que l'utilisateur soit prévenu, au lieu
                # d'attendre une synchronisation qui ne viendra pas.
                self._mark_expired(connection, exc, report)
        except ConnectorUnavailableError as exc:
            self._mark_unavailable(connection, exc, report)

        await self._session.flush()
        metrics.integration_syncs_total.labels(
            provider.value, "failed" if report.failed else "ok"
        ).inc()
        return report

    async def _pull(
        self, connection: IntegrationConnection, connector: object, report: SyncReport
    ) -> None:
        result = await connector.pull(cursor=connection.sync_cursor)  # type: ignore[attr-defined]

        if not result.incremental:
            # The provider says our cursor aged out. Clearing it makes the next
            # pass a full pull rather than a permanent silent failure.
            log.info("integration.cursor_expired", provider=connection.provider)
            connection.sync_cursor = None

        for item in result.items:
            outcome = await self._apply(connection, item)
            match outcome:
                case Resolution.CREATED:
                    report.created += 1
                case Resolution.UPDATED:
                    report.updated += 1
                case Resolution.DELETED:
                    report.deleted += 1
                case Resolution.CONFLICT:
                    report.conflicts += 1
                case _:
                    report.unchanged += 1

        if result.cursor:
            connection.sync_cursor = result.cursor

    async def _apply(self, connection: IntegrationConnection, item: RemoteItem) -> Resolution:
        """Fold one remote object into the corpus, idempotently."""
        link = (
            await self._session.execute(
                select(ExternalLink).where(
                    ExternalLink.connection_id == connection.id,
                    ExternalLink.external_id == item.external_id,
                )
            )
        ).scalar_one_or_none()

        entry = await self._session.get(Entry, link.entry_id) if link and link.entry_id else None

        outcome = resolve(
            remote_etag=item.etag,
            stored_etag=link.external_etag if link else None,
            remote_updated_at=item.updated_at,
            local_updated_at=entry.updated_at if entry else None,
            last_pulled_at=link.last_pulled_at if link else None,
            remote_deleted=item.deleted,
        )

        now = datetime.now(UTC)

        if outcome.resolution is Resolution.CONFLICT:
            # Flagged, not resolved. The user decides; last-write-wins here
            # would quietly discard whichever side they cared about.
            if link is not None:
                link.conflict_at = now
            metrics.integration_conflicts_total.labels(connection.provider).inc()
            return Resolution.CONFLICT

        if outcome.resolution is Resolution.DELETED:
            if link is not None:
                link.deleted_remotely_at = now
                if entry is not None:
                    # Marked, not deleted. Somebody removing an event from their
                    # calendar did not ask us to destroy the notes attached to
                    # it.
                    entry.status = EntryStatus.ARCHIVED.value
            return Resolution.DELETED

        if outcome.resolution is Resolution.UNCHANGED:
            return Resolution.UNCHANGED

        if entry is None:
            entry = Entry(
                account_id=connection.account_id,
                user_id=connection.user_id,
                entry_type=(
                    EntryType.TASK.value
                    if item.due_at is not None
                    else EntryType.MEETING.value
                    if item.starts_at is not None
                    else EntryType.NOTE.value
                ),
                title=item.title[:300],
                body=item.body,
                status=EntryStatus.ACTIVE.value,
                occurred_at=item.starts_at or item.updated_at or now,
                # Phase 1 already had this origin, unused until now. An
                # entry that came from a calendar must be distinguishable from
                # one a person typed — correction metrics count on it.
                origin=EntryOrigin.INTEGRATION.value,
            )
            self._session.add(entry)
            await self._session.flush()

            if item.due_at is not None:
                self._session.add(
                    Task(
                        entry_id=entry.id,
                        account_id=connection.account_id,
                        due_at=item.due_at,
                        completed_at=now if item.completed else None,
                    )
                )
        else:
            entry.title = item.title[:300]
            if item.body is not None:
                entry.body = item.body

        if link is None:
            link = ExternalLink(
                account_id=connection.account_id,
                connection_id=connection.id,
                provider=connection.provider,
                entry_id=entry.id,
                external_id=item.external_id,
            )
            self._session.add(link)

        link.external_etag = item.etag
        link.external_url = item.url
        link.last_pulled_at = now
        link.conflict_at = None
        await self._session.flush()
        return outcome.resolution

    async def conflicts(self) -> list[ExternalLink]:
        """Items the resolver refused to decide. Shown, not swept away."""
        return list(
            (
                await self._session.execute(
                    select(ExternalLink)
                    .where(ExternalLink.conflict_at.is_not(None))
                    .order_by(ExternalLink.conflict_at.desc())
                    .limit(100)
                )
            ).scalars()
        )

    async def resolve_conflict(self, link_id: uuid.UUID, *, keep: str) -> ExternalLink:
        """Settle a conflict the way the user chose.

        `keep` is `local` or `remote`. Recorded rather than silently applied:
        clearing the flag without saying which side won would leave the next
        sync free to reopen it.
        """
        link = await self._session.get(ExternalLink, link_id)
        if link is None:
            raise NotFoundError("Élément introuvable.")
        if keep not in ("local", "remote"):
            raise ValidationError("Choisissez « local » ou « remote ».", field="keep")

        link.conflict_at = None
        if keep == "remote":
            # Forcing the next pull to re-apply the remote version: clearing the
            # etag makes the resolver see it as changed.
            link.external_etag = None
        else:
            link.last_pushed_at = datetime.now(UTC)
        await self._session.flush()
        return link

    # -- Helpers -------------------------------------------------------------- #

    async def _run_pass(self, connection: IntegrationConnection, report: SyncReport) -> None:
        """Une passe, avec le jeton tel qu'il est maintenant.

        Le connecteur est reconstruit à chaque appel plutôt que réutilisé : il
        tient son jeton en attribut, donc un connecteur gardé au travers d'un
        renouvellement présenterait poliment l'ancien.
        """
        connector = build_connector(connection, access_token=self._token(connection))
        if Direction(connection.direction).reads:
            await self._pull(connection, connector, report)

    def _mark_expired(
        self, connection: IntegrationConnection, exc: Exception, report: SyncReport
    ) -> None:
        connection.status = "expired"
        connection.last_error = str(exc)[:500]
        report.failed = True
        report.reason = "Reconnexion requise."
        log.warning("integration.auth_expired", provider=connection.provider)

    def _mark_unavailable(
        self, connection: IntegrationConnection, exc: Exception, report: SyncReport
    ) -> None:
        connection.consecutive_failures += 1
        connection.last_error = str(exc)[:500]
        if connection.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            connection.status = "error"
            log.error("integration.gave_up", provider=connection.provider)
        report.failed = True
        report.reason = str(exc)

    async def _refresh(self, connection: IntegrationConnection) -> bool:
        """Renouvelle le jeton d'accès. Rend `True` si la connexion est repartie.

        Ne lève jamais : appelée depuis le chemin de synchronisation, qui a déjà
        sa façon de rendre compte d'un échec. Un `OAuthError` terminal marque la
        connexion `expired` — un octroi révoqué ne guérit pas —, tout le reste
        est laissé au compteur d'échecs.
        """
        provider = Provider(connection.provider)
        if not supports_oauth(provider) or not connection.refresh_token_encrypted:
            return False

        ring = self._ring()
        previous = decrypt(connection.refresh_token_encrypted, ring=ring)
        try:
            client = OAuthClient(
                provider_config(provider),
                credentials_for(provider, self._settings),
                redirect_uri=redirect_uri_for(provider, self._settings),
            )
            grant = (await client.refresh(refresh_token=previous)).merged_with(previous)
        except OAuthError as exc:
            if exc.terminal:
                connection.status = "expired"
                connection.last_error = str(exc)[:500]
                log.warning("integration.refresh_rejected", provider=provider.value)
            else:
                log.warning("integration.refresh_unavailable", provider=provider.value)
            await self._session.flush()
            return False

        connection.access_token_encrypted = encrypt(grant.access_token, ring=ring)
        # Microsoft fait tourner ses jetons de rafraîchissement, Google n'en
        # renvoie pas : `merged_with` a déjà conservé l'ancien le cas échéant,
        # donc écrire `None` ici signifierait vraiment « il n'y en a plus ».
        connection.refresh_token_encrypted = (
            encrypt(grant.refresh_token, ring=ring) if grant.refresh_token else None
        )
        connection.token_expires_at = grant.expires_at
        await self._session.flush()
        log.info("integration.refreshed", provider=provider.value)
        return True

    def _ring(self) -> KeyRing:
        return KeyRing.from_settings(self._settings.token_encryption_keys)

    def _token(self, connection: IntegrationConnection) -> str:
        if not connection.access_token_encrypted:
            return ""
        return decrypt(connection.access_token_encrypted, ring=self._ring())

    async def _connection(self, connection_id: uuid.UUID) -> IntegrationConnection:
        connection = await self._session.get(IntegrationConnection, connection_id)
        if connection is None or connection.user_id != self._principal.user_id:
            # A connection is personal, so another member's is not merely
            # forbidden — it is not theirs to see.
            raise NotFoundError("Connexion introuvable.")
        return connection
