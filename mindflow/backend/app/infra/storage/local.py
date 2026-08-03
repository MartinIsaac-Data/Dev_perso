"""Filesystem object store for local development and tests.

Mirrors the signed-URL contract of the real backend (ADR-018) rather than letting
the app upload through the API: if the local path allowed a shortcut, the
production path would be the only one ever exercised by hand, and the one nobody
tests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import quote

import anyio

from app.domain.errors import StorageError
from app.domain.ports import ObjectStoragePort, SignedUpload


class LocalObjectStorage(ObjectStoragePort):
    def __init__(self, root: str, *, base_url: str, secret: str, ttl_seconds: int) -> None:
        self._root = Path(root)
        self._base_url = base_url.rstrip("/")
        self._secret = secret.encode()
        self._ttl = ttl_seconds
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        # Reject traversal before touching the filesystem: object keys are built
        # from ids, but this is the last line before a path is resolved.
        if ".." in object_key or object_key.startswith("/"):
            raise StorageError("Clé d'objet invalide.")
        path = (self._root / object_key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise StorageError("Clé d'objet hors du répertoire de stockage.")
        return path

    def sign(self, object_key: str, expires_at: int) -> str:
        payload = f"{object_key}:{expires_at}".encode()
        digest = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def verify(self, object_key: str, expires_at: int, signature: str) -> bool:
        if expires_at < int(time.time()):
            return False
        return hmac.compare_digest(self.sign(object_key, expires_at), signature)

    async def signed_upload(
        self, object_key: str, *, media_type: str, max_bytes: int
    ) -> SignedUpload:
        expires_at = int(time.time()) + self._ttl
        signature = self.sign(object_key, expires_at)
        url = (
            f"{self._base_url}/v1/storage/{quote(object_key)}"
            f"?expires={expires_at}&signature={signature}"
        )
        return SignedUpload(
            url=url,
            method="PUT",
            headers={"content-type": media_type},
            expires_at=_iso(expires_at),
            object_key=object_key,
        )

    async def signed_download(self, object_key: str) -> str:
        expires_at = int(time.time()) + self._ttl
        signature = self.sign(object_key, expires_at)
        return (
            f"{self._base_url}/v1/storage/{quote(object_key)}"
            f"?expires={expires_at}&signature={signature}"
        )

    async def put(self, object_key: str, data: bytes) -> None:
        path = self._path(object_key)
        await anyio.to_thread.run_sync(lambda: path.parent.mkdir(parents=True, exist_ok=True))
        async with await anyio.open_file(path, "wb") as handle:
            await handle.write(data)

    async def download(self, object_key: str) -> bytes:
        path = self._path(object_key)
        if not path.exists():
            raise StorageError(f"Objet introuvable : {object_key}")
        async with await anyio.open_file(path, "rb") as handle:
            return await handle.read()

    async def delete(self, object_key: str) -> None:
        path = self._path(object_key)
        if path.exists():
            await anyio.to_thread.run_sync(path.unlink)

    async def exists(self, object_key: str) -> bool:
        return self._path(object_key).exists()


def _iso(epoch: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch, UTC).isoformat().replace("+00:00", "Z")
