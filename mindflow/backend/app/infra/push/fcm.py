"""Firebase Cloud Messaging, HTTP v1.

The legacy `/fcm/send` endpoint with a static server key is retired; v1 requires
a short-lived OAuth token obtained by signing a JWT with the service account's
private key. That is the whole of the extra machinery here.

One send per token, on purpose. FCM v1 has no true multicast endpoint — the
batch API multiplexes individual requests over one connection — and doing it
explicitly keeps the per-token error mapping honest: `UNREGISTERED` on one device
must retire *that* token, not the whole fan-out.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import jwt

from app.config import Settings
from app.domain.ports import PushMessage, PushResult, PushSenderPort
from app.observability.logging import get_logger

log = get_logger("push.fcm")

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 — an endpoint, not a secret
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
# Refresh a little before expiry so a request never races the rotation.
TOKEN_MARGIN = 120

# FCM error codes that mean "this token is dead, stop using it". Anything else is
# treated as transient: retiring a token on a temporary fault silently
# unsubscribes a user who did nothing wrong.
PERMANENT_ERRORS = frozenset(
    {
        "UNREGISTERED",
        "INVALID_ARGUMENT",
        "SENDER_ID_MISMATCH",
        "NOT_FOUND",
    }
)


class FcmPushSender(PushSenderPort):
    name = "fcm"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._credentials = _load_credentials(settings.fcm_service_account_json)

    @property
    def _project_id(self) -> str:
        return self._settings.fcm_project_id or str(self._credentials.get("project_id", ""))

    async def send(self, tokens: list[str], message: PushMessage) -> PushResult:
        if not tokens:
            return PushResult(delivered=0)
        if not self._credentials or not self._project_id:
            return PushResult(delivered=0, error="fcm_not_configured")

        try:
            access_token = await self._token()
        except (httpx.HTTPError, jwt.PyJWTError) as exc:
            log.error("push.fcm.auth_failed", error=type(exc).__name__)
            # Every token is retryable: the failure is ours, not the devices'.
            return PushResult(delivered=0, retryable_tokens=tuple(tokens), error="fcm_auth_failed")

        url = f"https://fcm.googleapis.com/v1/projects/{self._project_id}/messages:send"
        delivered = 0
        invalid: list[str] = []
        retryable: list[str] = []

        client = self._client or httpx.AsyncClient(timeout=self._settings.push_timeout_seconds)
        owns_client = self._client is None
        try:
            for token in tokens:
                try:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {access_token}"},
                        json={"message": _payload(token, message)},
                    )
                except httpx.HTTPError:
                    retryable.append(token)
                    continue

                if response.status_code < 300:
                    delivered += 1
                elif response.status_code in (400, 403, 404):
                    if _is_permanent(response):
                        invalid.append(token)
                    else:
                        retryable.append(token)
                else:
                    retryable.append(token)
        finally:
            if owns_client:
                await client.aclose()

        return PushResult(
            delivered=delivered,
            invalid_tokens=tuple(invalid),
            retryable_tokens=tuple(retryable),
        )

    async def _token(self) -> str:
        now = time.time()
        cached = self._access_token
        if cached is not None and now < self._expires_at - TOKEN_MARGIN:
            return cached

        assertion = jwt.encode(
            {
                "iss": self._credentials["client_email"],
                "scope": SCOPE,
                "aud": TOKEN_URL,
                "iat": int(now),
                "exp": int(now) + 3600,
            },
            self._credentials["private_key"],
            algorithm="RS256",
        )

        client = self._client or httpx.AsyncClient(timeout=self._settings.push_timeout_seconds)
        owns_client = self._client is None
        try:
            response = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            response.raise_for_status()
            body = response.json()
        finally:
            if owns_client:
                await client.aclose()

        self._access_token = str(body["access_token"])
        self._expires_at = now + float(body.get("expires_in", 3600))
        return self._access_token


def _payload(token: str, message: PushMessage) -> dict[str, Any]:
    """The v1 message body.

    `android.collapse_key` and `apns-collapse-id` are set from the same value so
    a second reminder about one task *replaces* the first on the lock screen
    instead of stacking. Notification stacking is the main reason people disable
    an app's notifications outright.
    """
    payload: dict[str, Any] = {
        "token": token,
        "notification": {"title": message.title, "body": message.body},
        "data": {key: str(value) for key, value in message.data.items()},
        "android": {
            "priority": "high",
            "notification": {
                "channel_id": "mindflow_reminders",
                "default_sound": True,
            },
        },
        "apns": {
            "payload": {
                "aps": {
                    "sound": "default",
                    "thread-id": message.collapse_key or "mindflow",
                }
            }
        },
    }
    if message.badge is not None:
        payload["apns"]["payload"]["aps"]["badge"] = message.badge
    if message.collapse_key:
        payload["android"]["collapse_key"] = message.collapse_key
        payload["apns"]["headers"] = {"apns-collapse-id": message.collapse_key[:64]}
    return payload


def _is_permanent(response: httpx.Response) -> bool:
    try:
        details = response.json().get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        return response.status_code == 404
    for detail in details:
        if isinstance(detail, dict) and detail.get("errorCode") in PERMANENT_ERRORS:
            return True
    return response.status_code == 404


def _load_credentials(raw: str) -> dict[str, Any]:
    """Service account JSON, from the environment.

    Malformed credentials disable push rather than crash the process: a bad key
    must not stop the API from serving requests that have nothing to do with
    notifications.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.error("push.fcm.bad_credentials", reason="not_json")
        return {}
    if not isinstance(parsed, dict) or "private_key" not in parsed:
        log.error("push.fcm.bad_credentials", reason="missing_private_key")
        return {}
    return parsed
