"""Encrypting OAuth tokens at rest.

A database backup restored onto a laptop must not be a set of live Google
credentials. Disk encryption does not help here: the backup is a file, and the
file leaves the encrypted disk the moment somebody downloads it.

**AES-256-GCM, not Fernet.** Fernet would have been one line shorter and uses
AES-128-CBC with an HMAC bolted on. GCM is authenticated by construction, is
what every provider's own SDK uses, and is the algorithm a security reviewer
expects to find.

**The key is versioned in the ciphertext.** Every value carries the id of the key
that produced it, so rotating means adding a key and re-encrypting in the
background rather than taking a maintenance window. A store that cannot be
rotated without downtime is a store that never gets rotated.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.observability.logging import get_logger

log = get_logger("crypto")

# 96 bits, the size GCM is defined for. A longer nonce is hashed down and gains
# nothing; a shorter one weakens it.
NONCE_BYTES = 12
KEY_BYTES = 32
_SEPARATOR = "$"


class DecryptionError(RuntimeError):
    """The value could not be decrypted.

    Raised rather than returning None so a caller cannot accidentally treat a
    failed decryption as "no token" and silently reconnect the user.
    """


@dataclass(frozen=True, slots=True)
class KeyRing:
    """The active key, plus any older keys still needed to read old rows.

    Reading uses whichever key the ciphertext names; writing always uses the
    active one. That asymmetry is the whole rotation strategy.
    """

    active_id: str
    keys: dict[str, bytes]

    def __post_init__(self) -> None:
        if self.active_id not in self.keys:
            raise ValueError(f"active key {self.active_id!r} is not in the ring")
        for key_id, material in self.keys.items():
            if len(material) != KEY_BYTES:
                raise ValueError(f"key {key_id!r} must be {KEY_BYTES} bytes, got {len(material)}")

    @classmethod
    def from_settings(cls, raw: str) -> KeyRing:
        """Parse `id:base64[,id:base64…]`, the active key first.

        A single string rather than a structured config because it has to
        survive being an environment variable in every deployment target we
        support, and because a secret manager hands back one value.
        """
        entries: dict[str, bytes] = {}
        first: str | None = None
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            key_id, _, material = chunk.partition(":")
            if not key_id or not material:
                raise ValueError("expected `id:base64` entries separated by commas")
            entries[key_id] = base64.urlsafe_b64decode(material)
            first = first or key_id
        if first is None:
            raise ValueError("no encryption key configured")
        return cls(active_id=first, keys=entries)


def generate_key() -> str:
    """A fresh key, base64-encoded, for an operator to put in a secret store."""
    return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode()


def encrypt(plaintext: str, *, ring: KeyRing) -> str:
    """Encrypt with the active key. Output is `v1$key_id$base64`.

    The key id travels with the ciphertext rather than being inferred from a
    column, so a row encrypted under a retired key stays readable after the
    active key changes.
    """
    if not plaintext:
        return ""
    nonce = os.urandom(NONCE_BYTES)
    cipher = AESGCM(ring.keys[ring.active_id])
    # The key id is authenticated as associated data: swapping it in a stored
    # value makes decryption fail rather than silently trying the wrong key.
    sealed = cipher.encrypt(nonce, plaintext.encode(), ring.active_id.encode())
    payload = base64.urlsafe_b64encode(nonce + sealed).decode()
    return f"v1{_SEPARATOR}{ring.active_id}{_SEPARATOR}{payload}"


def decrypt(value: str, *, ring: KeyRing) -> str:
    """Decrypt, using whichever key the ciphertext names."""
    if not value:
        return ""
    try:
        version, key_id, payload = value.split(_SEPARATOR, 2)
    except ValueError as exc:
        raise DecryptionError("format de chiffrement inattendu") from exc
    if version != "v1":
        raise DecryptionError(f"version de chiffrement inconnue : {version}")

    key = ring.keys.get(key_id)
    if key is None:
        # The operational failure this design exists to make legible: a key was
        # dropped from the ring while rows still referenced it.
        log.error("crypto.unknown_key", key_id=key_id)
        raise DecryptionError(f"clé {key_id} absente du trousseau")

    raw = base64.urlsafe_b64decode(payload)
    nonce, sealed = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, sealed, key_id.encode()).decode()
    except InvalidTag as exc:
        raise DecryptionError("valeur chiffrée altérée ou clé incorrecte") from exc


def needs_rotation(value: str, *, ring: KeyRing) -> bool:
    """Whether a stored value was written under a retired key.

    Read by the background re-encryption job. Rotation that requires a
    maintenance window is rotation that never happens.
    """
    if not value:
        return False
    parts = value.split(_SEPARATOR, 2)
    return len(parts) == 3 and parts[1] != ring.active_id
