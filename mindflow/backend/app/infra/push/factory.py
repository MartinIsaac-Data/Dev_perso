"""Push adapter selection.

One sender per provider, resolved from configuration. The dispatcher asks for
"the sender for FCM" and never learns which class it received — the same shape
as every other adapter boundary in this codebase (AI.md, I1).
"""

from __future__ import annotations

from collections.abc import Callable

from app.config import Settings
from app.domain.enums import PushProvider
from app.domain.ports import PushSenderPort
from app.infra.push.fake import FakePushSender

# Module-level so the OAuth token caches survive between jobs. Rebuilding the
# sender per batch would refetch a Google access token every minute.
_senders: dict[str, PushSenderPort] = {}


def build_push_sender(settings: Settings, provider: PushProvider) -> PushSenderPort | None:
    """The sender for one provider, or None when nothing can deliver.

    `local` and `none` legitimately have no server-side sender: a locally
    scheduled Windows toast is the client's job (ADR-040), and a device that
    never registered a token has nowhere to send to.
    """
    if provider in (PushProvider.LOCAL, PushProvider.NONE):
        return None

    if settings.push_backend == "fake":
        return _cached("fake", lambda: FakePushSender())

    if provider is PushProvider.FCM:
        from app.infra.push.fcm import FcmPushSender

        return _cached("fcm", lambda: FcmPushSender(settings))

    from app.infra.push.wns import WnsPushSender

    return _cached("wns", lambda: WnsPushSender(settings))


def _cached(key: str, build: Callable[[], PushSenderPort]) -> PushSenderPort:
    sender = _senders.get(key)
    if sender is None:
        sender = build()
        _senders[key] = sender
    return sender


def reset_senders() -> None:
    """Test hook — settings change between cases."""
    _senders.clear()
