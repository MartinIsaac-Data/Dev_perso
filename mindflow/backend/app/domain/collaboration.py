"""Comments, mentions, and share links.

Small module, three ideas that each have a way of going wrong.

**A mention is parsed once, on write, and stored as a row.** The tempting design
is to keep the raw text and resolve `@sylvie` at render time. It fails the day
Sylvie is renamed or leaves: old comments start pointing at nobody, or worse, at
whoever took the handle. Resolving on write freezes who was meant.

**A share link is a capability, not an identity.** Anyone holding it can read;
that is the point, and it is also the risk. So links expire by default, carry a
revocation timestamp rather than being deleted (a deleted link is a link nobody
can explain afterwards), and their tokens are stored hashed — a leaked database
must not be a leaked set of live links.

**Mention notification is a side effect of the comment, not of the mention.** One
comment mentioning three people is one event to each of them, never three events
about one comment to the whole thread.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

# `@` followed by a handle. Deliberately narrow: letters, digits, dot, dash,
# underscore. An email address inside a comment must not become a mention, so
# the pattern stops at `@`-preceded-by-a-word-character.
_MENTION = re.compile(r"(?<![\w@])@([a-zA-Z0-9][\w.\-]{1,63})")

MAX_MENTIONS_PER_COMMENT = 20
MAX_COMMENT_LENGTH = 4000

# How long a share link lives unless the creator says otherwise. Thirty days is
# long enough for a review cycle and short enough that a link pasted into a chat
# two years ago is not still live.
DEFAULT_SHARE_TTL = timedelta(days=30)


class ShareScope(StrEnum):
    """What a link exposes. Narrower than the resource, never wider."""

    ENTRY = "entry"
    WORKSPACE = "workspace"

    @property
    def label(self) -> str:
        return {ShareScope.ENTRY: "Note", ShareScope.WORKSPACE: "Espace"}[self]


class CommentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class ParsedMention:
    handle: str
    start: int
    end: int


def parse_mentions(body: str) -> list[ParsedMention]:
    """Find the handles a comment mentions, in order, deduplicated.

    Deduplicated by handle rather than by occurrence: writing « @paul, and also
    @paul » is one notification to Paul, not two. The offsets kept are those of
    the first occurrence, which is where a client should place the first link.
    """
    seen: dict[str, ParsedMention] = {}
    for match in _MENTION.finditer(body):
        handle = match.group(1).lower().rstrip(".")
        if not handle or handle in seen:
            continue
        if len(seen) >= MAX_MENTIONS_PER_COMMENT:
            # A comment mentioning fifty people is a broadcast, and broadcasts
            # are how notification systems get muted. Silently capped rather
            # than rejected: the comment is still worth saving.
            break
        seen[handle] = ParsedMention(handle=handle, start=match.start(), end=match.end())
    return list(seen.values())


def handle_for(email: str, *, display_name: str | None = None) -> str:
    """The handle a person is mentioned by.

    Derived from the email local part rather than from the display name,
    because display names collide constantly inside one company and email local
    parts cannot. `marie.dupont@…` becomes `marie.dupont`.
    """
    local = email.split("@", 1)[0].strip().lower()
    cleaned = re.sub(r"[^\w.\-]", "", local)
    if cleaned:
        return cleaned[:64]
    # An email with no usable local part is possible in test data and in some
    # federated identity setups. Falling back to the display name is better
    # than producing an empty handle nobody can type.
    fallback = re.sub(r"[^\w]", "", (display_name or "membre").lower())
    return (fallback or "membre")[:64]


@dataclass(frozen=True, slots=True)
class ShareToken:
    """A freshly minted link secret and the digest to store.

    The plaintext is returned exactly once, to the creator. Only the digest is
    persisted, so a database dump is not a set of live links.
    """

    plaintext: str
    digest: str

    @property
    def suffix(self) -> str:
        """The last characters, shown in the UI so a user can tell two links
        apart without either one being readable from a screenshot."""
        return self.plaintext[-6:]


def mint_share_token() -> ShareToken:
    # 32 bytes of urandom, URL-safe. Long enough that enumeration is not a
    # threat model worth writing a rate limiter for.
    plaintext = secrets.token_urlsafe(32)
    return ShareToken(plaintext=plaintext, digest=hash_share_token(plaintext))


def hash_share_token(plaintext: str) -> str:
    """SHA-256 of the token.

    Not a password hash, and deliberately not: the input is 256 bits of
    uniform randomness, so there is no dictionary to attack and stretching it
    would only slow down every legitimate resolution.
    """
    return hashlib.sha256(plaintext.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ShareValidity:
    valid: bool
    reason: str = ""


def check_share(
    *,
    revoked_at: datetime | None,
    expires_at: datetime | None,
    now: datetime,
) -> ShareValidity:
    """Whether a link may still be used.

    Revocation is checked before expiry so that a deliberately killed link
    reports as killed rather than as expired — the two mean different things to
    the person who follows it, and to the person auditing later.
    """
    if revoked_at is not None:
        return ShareValidity(False, "Ce lien a été révoqué.")
    if expires_at is not None and expires_at <= now:
        return ShareValidity(False, "Ce lien a expiré.")
    return ShareValidity(True)


def default_expiry(now: datetime, *, ttl: timedelta = DEFAULT_SHARE_TTL) -> datetime:
    return now + ttl
