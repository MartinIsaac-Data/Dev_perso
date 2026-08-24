"""L'échange de jetons, côté fil.

Pas de SDK fournisseur, du `httpx` et des paramètres de formulaire — même
discipline que les connecteurs et les adaptateurs IA (ADR-045). Un flux OAuth
tient en deux requêtes POST ; trois arbres de dépendances pour les écrire
seraient trois façons d'être cassé par une mise à jour que personne n'a
demandée.

**Le `state` est chiffré, pas seulement signé.** Il transporte le vérificateur
PKCE, qui doit rester secret : signé, il serait lisible dans la barre d'adresse
et PKCE ne protégerait plus de rien. Chiffré avec le trousseau d'ADR-058, il est
opaque au navigateur et déchiffrable par nous seuls — ce qui permet au passage
de ne rien stocker entre l'autorisation et le retour. Pas de table, pas de
Redis, pas de session à expirer : l'état vit dans l'aller-retour.

Il porte aussi l'identité de qui a demandé. Sans cela, un `state` valide d'un
utilisateur pourrait rattacher un compte Google à la connexion d'un autre.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.domain.oauth import (
    STATE_TTL,
    OAuthError,
    OAuthProvider,
    TokenGrant,
    expiry_from,
)
from app.domain.sync import Provider
from app.infra.crypto import DecryptionError, KeyRing, decrypt, encrypt
from app.observability.logging import get_logger

log = get_logger("oauth")

TIMEOUT = httpx.Timeout(15.0)

# Les codes d'erreur OAuth qui signifient « cet octroi est mort ». Tout le reste
# — panne réseau, 500 du fournisseur, limite de débit — est réessayable, et les
# confondre donne soit des reconnexions demandées pour rien, soit un compteur
# d'échecs qui monte contre un jeton qui ne reviendra jamais.
TERMINAL_ERRORS = frozenset(
    {"invalid_grant", "invalid_client", "unauthorized_client", "invalid_scope"}
)


@dataclass(frozen=True, slots=True)
class OAuthCredentials:
    client_id: str
    client_secret: str


@dataclass(frozen=True, slots=True)
class StatePayload:
    account_id: uuid.UUID
    user_id: uuid.UUID
    provider: Provider
    verifier: str
    issued_at: datetime


def credentials_for(provider: Provider, settings: Settings) -> OAuthCredentials:
    """Les identifiants d'application, ou une erreur qui dit lequel manque.

    Une application non configurée est une erreur d'exploitation, pas une panne
    : le message nomme la variable à renseigner plutôt que de laisser le
    fournisseur répondre un `invalid_client` opaque.
    """
    pairs = {
        Provider.GOOGLE_CALENDAR: (
            settings.google_client_id,
            settings.google_client_secret,
            "MINDFLOW_GOOGLE_CLIENT_ID / MINDFLOW_GOOGLE_CLIENT_SECRET",
        ),
        Provider.OUTLOOK_CALENDAR: (
            settings.microsoft_client_id,
            settings.microsoft_client_secret,
            "MINDFLOW_MICROSOFT_CLIENT_ID / MINDFLOW_MICROSOFT_CLIENT_SECRET",
        ),
        Provider.MICROSOFT_TODO: (
            settings.microsoft_client_id,
            settings.microsoft_client_secret,
            "MINDFLOW_MICROSOFT_CLIENT_ID / MINDFLOW_MICROSOFT_CLIENT_SECRET",
        ),
    }
    entry = pairs.get(provider)
    if entry is None:
        raise OAuthError(f"{provider.label} ne passe pas par OAuth.", terminal=True)
    client_id, client_secret, names = entry
    if not client_id or not client_secret:
        raise OAuthError(
            f"{provider.label} n'est pas configuré : renseignez {names}.", terminal=True
        )
    return OAuthCredentials(client_id=client_id, client_secret=client_secret)


def redirect_uri_for(provider: Provider, settings: Settings) -> str:
    """L'adresse de retour, dérivée d'une seule source.

    Elle doit être identique à l'octet près entre la demande d'autorisation,
    l'échange, et ce qui est déclaré chez le fournisseur — sinon
    `redirect_uri_mismatch`, l'erreur la plus fréquente d'un premier
    branchement. La dériver plutôt que la configurer deux fois supprime la
    moitié des occasions de se tromper.
    """
    return f"{settings.public_base_url.rstrip('/')}/integrations/{provider.value}/callback"


# -- Le `state` --------------------------------------------------------------- #


def encode_state(
    *,
    ring: KeyRing,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    provider: Provider,
    verifier: str,
    issued_at: datetime | None = None,
) -> str:
    payload = {
        "a": str(account_id),
        "u": str(user_id),
        "p": provider.value,
        "v": verifier,
        "t": (issued_at or datetime.now(UTC)).isoformat(),
    }
    return encrypt(json.dumps(payload, separators=(",", ":")), ring=ring)


def decode_state(state: str, *, ring: KeyRing, now: datetime | None = None) -> StatePayload:
    """Déchiffre et valide. Toute anomalie est terminale.

    Un `state` illisible n'est pas un incident réseau : c'est un retour forgé,
    rejoué, ou une demande abandonnée depuis un quart d'heure. Aucun de ces cas
    ne se répare en réessayant.
    """
    try:
        raw = json.loads(decrypt(state, ring=ring))
    except (DecryptionError, json.JSONDecodeError, ValueError) as exc:
        log.warning("oauth.state_rejected", reason=type(exc).__name__)
        raise OAuthError("Demande d'autorisation invalide.", terminal=True) from exc

    try:
        issued_at = datetime.fromisoformat(str(raw["t"]))
        payload = StatePayload(
            account_id=uuid.UUID(str(raw["a"])),
            user_id=uuid.UUID(str(raw["u"])),
            provider=Provider(str(raw["p"])),
            verifier=str(raw["v"]),
            issued_at=issued_at,
        )
    except (KeyError, ValueError) as exc:
        log.warning("oauth.state_malformed")
        raise OAuthError("Demande d'autorisation invalide.", terminal=True) from exc

    if payload.issued_at.tzinfo is None:
        payload = StatePayload(
            account_id=payload.account_id,
            user_id=payload.user_id,
            provider=payload.provider,
            verifier=payload.verifier,
            issued_at=payload.issued_at.replace(tzinfo=UTC),
        )
    if (now or datetime.now(UTC)) - payload.issued_at > STATE_TTL:
        raise OAuthError("Demande d'autorisation expirée. Recommencez.", terminal=True)
    return payload


# -- Les deux requêtes -------------------------------------------------------- #


class OAuthClient:
    def __init__(
        self,
        config: OAuthProvider,
        credentials: OAuthCredentials,
        *,
        redirect_uri: str,
    ) -> None:
        self._config = config
        self._credentials = credentials
        self._redirect_uri = redirect_uri

    def authorisation_url(self, *, state: str, challenge: str) -> str:
        params = {
            "client_id": self._credentials.client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": self._config.scope_value,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            **self._config.extra_authorize_params,
        }
        return f"{self._config.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, verifier: str) -> TokenGrant:
        return await self._post(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "code_verifier": verifier,
            }
        )

    async def refresh(self, *, refresh_token: str) -> TokenGrant:
        return await self._post(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                # Renvoyée par certains fournisseurs, ignorée par les autres :
                # Microsoft exige que la portée demandée au renouvellement soit
                # incluse dans celle de l'octroi initial.
                "scope": self._config.scope_value,
            }
        )

    async def _post(self, form: dict[str, str]) -> TokenGrant:
        body = {
            **form,
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    self._config.exchange_url,
                    data=body,
                    headers={"accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            # Réessayable : le fournisseur n'a rien dit, il n'a pas répondu.
            raise OAuthError("Fournisseur d'identité injoignable.") from exc

        if response.status_code >= 400:
            raise _error_from(response, provider=self._config.provider)

        try:
            payload = response.json()
        except ValueError as exc:
            raise OAuthError("Réponse illisible du fournisseur d'identité.") from exc

        access_token = str(payload.get("access_token") or "")
        if not access_token:
            # Une réponse 200 sans jeton : contrat rompu, pas panne passagère.
            raise OAuthError("Aucun jeton d'accès dans la réponse.", terminal=True)

        refresh_token = payload.get("refresh_token")
        return TokenGrant(
            access_token=access_token,
            refresh_token=str(refresh_token) if refresh_token else None,
            expires_at=expiry_from(payload.get("expires_in")),
            scope=str(payload.get("scope") or ""),
        )


def _error_from(response: httpx.Response, *, provider: Provider) -> OAuthError:
    code = ""
    description = ""
    try:
        payload = response.json()
        code = str(payload.get("error") or "")
        description = str(payload.get("error_description") or "")
    except ValueError:
        pass

    terminal = code in TERMINAL_ERRORS
    # Le corps n'est jamais journalisé : une réponse d'erreur de jetons peut
    # contenir la requête qui l'a produite, donc le secret client.
    log.warning(
        "oauth.exchange_failed",
        provider=provider.value,
        status=response.status_code,
        error=code or "unknown",
        terminal=terminal,
    )
    if terminal:
        return OAuthError(
            "Autorisation refusée par le fournisseur. Reconnectez le service.",
            terminal=True,
        )
    return OAuthError(
        f"Échange de jetons impossible ({response.status_code}). {description}".strip()
    )
