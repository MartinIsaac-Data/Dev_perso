"""Windows Notification Service.

Windows is the one platform in this product with two genuinely different
delivery paths, and the difference is not cosmetic:

* A **packaged** app (MSIX, from the Store) gets a WNS channel URI and receives
  server-pushed toasts even when it is not running. That is this adapter.
* An **unpackaged** app (a plain `.exe`, which is what `flutter build windows`
  produces by default) has no channel URI. Its notifications are scheduled
  *locally* by the client from the reminder list — which is why `reminder`
  carries a `local` channel and why the client syncs it (ADR-040).

Getting this wrong in either direction produces the same user-visible bug: a
reminder that never fires. So the provider is stored per device rather than
inferred from the platform.

Payload format is XML, not JSON — WNS predates the convention and has not moved.
"""

from __future__ import annotations

import time
from xml.sax.saxutils import escape

import httpx

from app.config import Settings
from app.domain.ports import PushMessage, PushResult, PushSenderPort
from app.observability.logging import get_logger

log = get_logger("push.wns")

TOKEN_URL = "https://login.live.com/accesstoken.srf"  # noqa: S105 — an endpoint, not a secret
SCOPE = "notify.windows.com"
TOKEN_MARGIN = 120

# 404: the channel no longer exists. 410: the app was uninstalled. Both are
# permanent, and retrying either forever is how a dead-token table grows without
# bound.
PERMANENT_STATUSES = frozenset({404, 410})


class WnsPushSender(PushSenderPort):
    name = "wns"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    async def send(self, tokens: list[str], message: PushMessage) -> PushResult:
        if not tokens:
            return PushResult(delivered=0)
        if not (self._settings.wns_client_id and self._settings.wns_client_secret):
            return PushResult(delivered=0, error="wns_not_configured")

        try:
            access_token = await self._token()
        except httpx.HTTPError as exc:
            log.error("push.wns.auth_failed", error=type(exc).__name__)
            return PushResult(delivered=0, retryable_tokens=tuple(tokens), error="wns_auth_failed")

        body = _toast_xml(message)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "text/xml",
            "X-WNS-Type": "wns/toast",
        }
        if message.collapse_key:
            # WNS replaces a toast carrying the same tag, which is how a second
            # reminder about one task updates the first instead of stacking.
            headers["X-WNS-Tag"] = message.collapse_key[:16]

        delivered = 0
        invalid: list[str] = []
        retryable: list[str] = []

        client = self._client or httpx.AsyncClient(timeout=self._settings.push_timeout_seconds)
        owns_client = self._client is None
        try:
            for channel_uri in tokens:
                try:
                    response = await client.post(channel_uri, headers=headers, content=body)
                except httpx.HTTPError:
                    retryable.append(channel_uri)
                    continue
                if response.status_code < 300:
                    delivered += 1
                elif response.status_code in PERMANENT_STATUSES:
                    invalid.append(channel_uri)
                else:
                    retryable.append(channel_uri)
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

        client = self._client or httpx.AsyncClient(timeout=self._settings.push_timeout_seconds)
        owns_client = self._client is None
        try:
            response = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._settings.wns_client_id,
                    "client_secret": self._settings.wns_client_secret,
                    "scope": SCOPE,
                },
            )
            response.raise_for_status()
            body = response.json()
        finally:
            if owns_client:
                await client.aclose()

        self._access_token = str(body["access_token"])
        self._expires_at = now + float(body.get("expires_in", 86400))
        return self._access_token


def _toast_xml(message: PushMessage) -> bytes:
    """A `ToastGeneric` toast.

    Everything interpolated is XML-escaped: a task titled `Rappeler <DAF> & co`
    would otherwise produce a malformed document, and WNS answers a malformed
    document with a 400 that looks exactly like a configuration problem.
    """
    launch = "&amp;".join(
        f"{escape(key)}={escape(str(value))}" for key, value in sorted(message.data.items())
    )
    return (
        f'<toast launch="{launch}">'
        f'<visual><binding template="ToastGeneric">'
        f"<text>{escape(message.title)}</text>"
        f"<text>{escape(message.body)}</text>"
        f"</binding></visual>"
        f"</toast>"
    ).encode()
