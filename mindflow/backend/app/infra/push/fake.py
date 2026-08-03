"""In-memory push sender.

Used by tests and by `docker compose up` without Firebase credentials. Records
what it was asked to send so a test can assert on the *content* of a
notification, not merely that one was attempted — the interesting bugs in this
area are wrong titles and missing routing data, not missing calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.ports import PushMessage, PushResult, PushSenderPort
from app.observability.logging import get_logger

log = get_logger("push.fake")


@dataclass
class SentPush:
    tokens: list[str]
    message: PushMessage


@dataclass
class FakePushSender(PushSenderPort):
    name: str = "fake"
    sent: list[SentPush] = field(default_factory=list)
    # Tokens this fake pretends are dead, so the retirement path is testable.
    dead_tokens: set[str] = field(default_factory=set)
    fail_with: str | None = None

    async def send(self, tokens: list[str], message: PushMessage) -> PushResult:
        if self.fail_with is not None:
            return PushResult(delivered=0, retryable_tokens=tuple(tokens), error=self.fail_with)
        live = [token for token in tokens if token not in self.dead_tokens]
        self.sent.append(SentPush(tokens=list(tokens), message=message))
        log.info("push.fake.sent", count=len(live), title=message.title)
        return PushResult(
            delivered=len(live),
            invalid_tokens=tuple(t for t in tokens if t in self.dead_tokens),
        )
