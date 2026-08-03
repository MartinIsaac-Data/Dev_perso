"""Supabase Auth token verification (ADR-029).

The backend does not issue tokens; it verifies Supabase's. Two signing schemes
are supported because Supabase projects use either:

* **HS256** with the project JWT secret (legacy projects), and
* **asymmetric keys** published through JWKS (current projects).

Verification is local — no network call on the request path except the JWKS fetch,
which is cached. That matters: an auth check that depends on a third party's
availability would put every request behind their uptime.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.config import Settings
from app.domain.errors import AuthError, TokenExpiredError, TokenInvalidError
from app.observability.logging import get_logger

log = get_logger("auth")

# Supabase never issues `none`; listing algorithms explicitly prevents the
# classic algorithm-confusion attack where a forged token claims alg=none.
HS_ALGORITHMS = ["HS256"]
ASYMMETRIC_ALGORITHMS = ["RS256", "ES256"]


@dataclass(frozen=True, slots=True)
class Claims:
    """The subset of the token we act on. Everything else is ignored."""

    subject: str
    email: str | None
    role: str
    session_id: str | None
    expires_at: int
    raw: dict[str, Any]


class TokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client: PyJWKClient | None = None
        if settings.supabase_jwks_url:
            # PyJWKClient caches keys and refreshes on unknown `kid`, so a key
            # rotation does not require a redeploy.
            self._jwks_client = PyJWKClient(
                settings.supabase_jwks_url, cache_keys=True, lifespan=3600
            )

    def verify(self, token: str) -> Claims:
        if not token:
            raise AuthError("Jeton absent.")

        try:
            payload = self._decode(token)
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Le jeton a expiré.") from exc
        except jwt.InvalidAudienceError as exc:
            raise TokenInvalidError("Audience du jeton invalide.") from exc
        except jwt.InvalidTokenError as exc:
            # Deliberately vague to the caller: the reason a token is invalid is
            # information an attacker can use to iterate.
            log.info("auth.token_rejected", reason=type(exc).__name__)
            raise TokenInvalidError("Jeton invalide.") from exc

        subject = payload.get("sub")
        if not subject:
            raise TokenInvalidError("Jeton sans identifiant de sujet.")

        return Claims(
            subject=str(subject),
            email=payload.get("email"),
            role=payload.get("role", "authenticated"),
            session_id=payload.get("session_id"),
            expires_at=int(payload.get("exp", 0)),
            raw=payload,
        )

    def _decode(self, token: str) -> dict[str, Any]:
        leeway = self._settings.jwt_leeway_seconds
        audience = self._settings.jwt_audience

        if self._jwks_client is not None:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=ASYMMETRIC_ALGORITHMS,
                audience=audience,
                leeway=leeway,
                options={"require": ["exp", "sub"]},
            )

        if self._settings.supabase_jwt_secret:
            return jwt.decode(
                token,
                self._settings.supabase_jwt_secret,
                algorithms=HS_ALGORITHMS,
                audience=audience,
                leeway=leeway,
                options={"require": ["exp", "sub"]},
            )

        if self._settings.is_production_like:
            # Unreachable: Settings refuses to build in this state. Kept as a
            # second barrier because the cost of being wrong here is total.
            raise AuthError("Aucune méthode de vérification de jeton configurée.")

        return self._decode_unverified_for_local_development(token)

    def _decode_unverified_for_local_development(self, token: str) -> dict[str, Any]:
        """Local and test only.

        Settings.\\_check_production_requirements makes it impossible to reach
        this branch in staging or prod; the guard above is the second lock.
        """
        log.warning("auth.unverified_token_accepted", env=self._settings.env)
        return jwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False, "require": ["sub"]},
            algorithms=HS_ALGORITHMS + ASYMMETRIC_ALGORITHMS,
        )


class SupabaseAdminClient:
    """Thin client over the Supabase admin API.

    Used only for out-of-band operations (deleting a user on account deletion).
    Never on the request path.
    """

    def __init__(self, settings: Settings) -> None:
        self._base = settings.supabase_url.rstrip("/")
        self._key = settings.supabase_service_key

    async def delete_user(self, subject: str) -> None:
        if not self._base or not self._key:
            log.warning("auth.admin_not_configured", action="delete_user")
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{self._base}/auth/v1/admin/users/{subject}",
                headers={"apikey": self._key, "Authorization": f"Bearer {self._key}"},
            )
            if response.status_code not in (200, 204, 404):
                log.error("auth.delete_user_failed", status=response.status_code)


def make_local_token(subject: str, email: str, *, expires_in: int = 3600) -> str:
    """Mint an unsigned token for local development and tests.

    Exists so the whole stack can be exercised without a Supabase project. It is
    rejected in staging and prod, where signature verification is mandatory.
    """
    payload = {
        "sub": subject,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + expires_in,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, "local-development-only", algorithm="HS256")
