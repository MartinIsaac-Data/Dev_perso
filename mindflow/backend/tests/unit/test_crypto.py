"""Token encryption at rest.

The property being defended: a database backup restored onto somebody's laptop
must not be a set of live Google credentials. Disk encryption does not help —
the backup is a file, and it leaves the encrypted disk the moment anyone
downloads it.

`TestRotation` is the half that usually goes missing. A key store that cannot be
rotated without a maintenance window is a key store that never gets rotated.
"""

from __future__ import annotations

import base64
import os

import pytest

from app.infra.crypto import (
    DecryptionError,
    KeyRing,
    decrypt,
    encrypt,
    generate_key,
    needs_rotation,
)


def _ring(*ids: str) -> KeyRing:
    keys = {key_id: os.urandom(32) for key_id in ids}
    return KeyRing(active_id=ids[0], keys=keys)


class TestRoundTrip:
    def test_a_token_survives_encryption(self) -> None:
        ring = _ring("k1")
        secret = "ya29.a0AfH6SMBxxx-refresh-token"
        assert decrypt(encrypt(secret, ring=ring), ring=ring) == secret

    def test_the_ciphertext_does_not_contain_the_plaintext(self) -> None:
        ring = _ring("k1")
        sealed = encrypt("super-secret-token", ring=ring)
        assert "super-secret-token" not in sealed

    def test_encrypting_twice_gives_different_ciphertexts(self) -> None:
        # A fresh nonce each time. Deterministic output would leak equality:
        # two users with the same token would be visibly identical in a dump.
        ring = _ring("k1")
        assert encrypt("same", ring=ring) != encrypt("same", ring=ring)

    def test_an_empty_value_stays_empty(self) -> None:
        # A connection with no refresh token is normal; it must not become a
        # ciphertext of the empty string that later decrypts to something.
        ring = _ring("k1")
        assert encrypt("", ring=ring) == ""
        assert decrypt("", ring=ring) == ""

    def test_unicode_survives(self) -> None:
        ring = _ring("k1")
        secret = "jeton-avec-accents-éàü-🔐"
        assert decrypt(encrypt(secret, ring=ring), ring=ring) == secret


class TestTampering:
    def test_a_modified_ciphertext_is_refused(self) -> None:
        # GCM is authenticated by construction, which is why it was chosen over
        # Fernet's CBC-plus-HMAC.
        ring = _ring("k1")
        sealed = encrypt("token", ring=ring)
        version, key_id, payload = sealed.split("$", 2)
        raw = bytearray(base64.urlsafe_b64decode(payload))
        raw[-1] ^= 0xFF
        tampered = f"{version}${key_id}${base64.urlsafe_b64encode(bytes(raw)).decode()}"

        with pytest.raises(DecryptionError):
            decrypt(tampered, ring=ring)

    def test_swapping_the_key_id_is_refused(self) -> None:
        # The key id is authenticated as associated data, so relabelling a
        # value fails loudly instead of silently trying the wrong key.
        ring = _ring("k1", "k2")
        sealed = encrypt("token", ring=ring)
        relabelled = sealed.replace("$k1$", "$k2$", 1)

        with pytest.raises(DecryptionError):
            decrypt(relabelled, ring=ring)

    def test_a_wrong_key_is_refused(self) -> None:
        sealed = encrypt("token", ring=_ring("k1"))
        with pytest.raises(DecryptionError):
            decrypt(sealed, ring=_ring("k1"))  # same id, different material

    def test_garbage_is_refused_rather_than_returning_none(self) -> None:
        # Raising rather than returning None so a caller cannot treat a failed
        # decryption as "no token" and silently reconnect the user.
        with pytest.raises(DecryptionError):
            decrypt("not-a-ciphertext", ring=_ring("k1"))

    def test_an_unknown_version_is_refused(self) -> None:
        with pytest.raises(DecryptionError, match="version"):
            decrypt("v9$k1$abc", ring=_ring("k1"))


class TestRotation:
    def test_a_value_written_under_an_old_key_still_reads(self) -> None:
        # The whole rotation strategy: read with whichever key the ciphertext
        # names, write with the active one.
        old = _ring("k1")
        sealed = encrypt("token", ring=old)

        rotated = KeyRing(active_id="k2", keys={**old.keys, "k2": os.urandom(32)})
        assert decrypt(sealed, ring=rotated) == "token"

    def test_new_values_use_the_active_key(self) -> None:
        old = _ring("k1")
        rotated = KeyRing(active_id="k2", keys={**old.keys, "k2": os.urandom(32)})
        assert encrypt("token", ring=rotated).split("$")[1] == "k2"

    def test_stale_values_are_identifiable(self) -> None:
        # Read by the background re-encryption job, which is what makes
        # rotation possible without a maintenance window.
        old = _ring("k1")
        sealed = encrypt("token", ring=old)
        rotated = KeyRing(active_id="k2", keys={**old.keys, "k2": os.urandom(32)})

        assert needs_rotation(sealed, ring=rotated)
        assert not needs_rotation(encrypt("token", ring=rotated), ring=rotated)

    def test_an_empty_value_needs_no_rotation(self) -> None:
        assert not needs_rotation("", ring=_ring("k1"))

    def test_dropping_a_key_still_in_use_fails_legibly(self) -> None:
        # The operational failure this design exists to make visible.
        sealed = encrypt("token", ring=_ring("k1"))
        with pytest.raises(DecryptionError, match="absente du trousseau"):
            decrypt(sealed, ring=_ring("k2"))


class TestKeyRing:
    def test_the_active_key_must_be_in_the_ring(self) -> None:
        with pytest.raises(ValueError, match="active key"):
            KeyRing(active_id="missing", keys={"k1": os.urandom(32)})

    def test_a_short_key_is_refused_at_construction(self) -> None:
        # Better to fail at startup than to encrypt everything with 16 bytes.
        with pytest.raises(ValueError, match="32 bytes"):
            KeyRing(active_id="k1", keys={"k1": os.urandom(16)})

    def test_parses_the_environment_form(self) -> None:
        # One string, because it has to survive being an environment variable
        # in every deployment target and because a secret manager hands back
        # one value.
        first, second = generate_key(), generate_key()
        ring = KeyRing.from_settings(f"2026-08:{first}, 2025-01:{second}")

        assert ring.active_id == "2026-08"
        assert set(ring.keys) == {"2026-08", "2025-01"}

    def test_the_first_entry_is_the_active_one(self) -> None:
        ring = KeyRing.from_settings(f"new:{generate_key()},old:{generate_key()}")
        assert ring.active_id == "new"

    def test_an_empty_configuration_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no encryption key"):
            KeyRing.from_settings("")

    def test_a_malformed_entry_is_refused(self) -> None:
        with pytest.raises(ValueError, match="id:base64"):
            KeyRing.from_settings("just-a-key-with-no-id")

    def test_generated_keys_are_the_right_size(self) -> None:
        assert len(base64.urlsafe_b64decode(generate_key())) == 32
