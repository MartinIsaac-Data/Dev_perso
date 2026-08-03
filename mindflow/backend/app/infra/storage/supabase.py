"""Supabase Storage adapter (ADR-030).

Uses Supabase's *signed upload URL* endpoint so audio goes client → storage
directly and never transits the API (ADR-018). The service key stays server-side;
the client only ever receives a short-lived, single-object token.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.domain.errors import StorageError
from app.domain.ports import ObjectStoragePort, SignedUpload
from app.observability.logging import get_logger

log = get_logger("storage.supabase")


class SupabaseObjectStorage(ObjectStoragePort):
    def __init__(
        self,
        *,
        base_url: str,
        service_key: str,
        bucket: str,
        ttl_seconds: int,
        timeout: float = 15.0,
    ) -> None:
        if not base_url or not service_key:
            raise StorageError("Supabase Storage requiert supabase_url et supabase_service_key.")
        self._base = f"{base_url.rstrip('/')}/storage/v1"
        self._key = service_key
        self._bucket = bucket
        self._ttl = ttl_seconds
        self._timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"apikey": self._key, "Authorization": f"Bearer {self._key}"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, headers=self._headers)

    async def signed_upload(
        self, object_key: str, *, media_type: str, max_bytes: int
    ) -> SignedUpload:
        async with self._client() as client:
            response = await client.post(
                f"{self._base}/object/upload/sign/{self._bucket}/{object_key}"
            )
        if response.status_code >= 400:
            log.error("storage.sign_upload_failed", status=response.status_code)
            raise StorageError("Impossible de préparer l'envoi de l'audio.")

        token = response.json().get("url", "")
        # Supabase returns a relative path carrying the token; make it absolute.
        url = f"{self._base}{token}" if token.startswith("/") else token
        expires_at = datetime.now(UTC) + timedelta(seconds=self._ttl)
        return SignedUpload(
            url=url,
            method="PUT",
            headers={
                "content-type": media_type,
                "x-upsert": "false",
                # Advisory only — the real ceiling is enforced by the bucket
                # policy, because a header can be edited by the client.
                "cache-control": "3600",
            },
            expires_at=expires_at.isoformat().replace("+00:00", "Z"),
            object_key=object_key,
        )

    async def signed_download(self, object_key: str) -> str:
        async with self._client() as client:
            response = await client.post(
                f"{self._base}/object/sign/{self._bucket}/{object_key}",
                json={"expiresIn": self._ttl},
            )
        if response.status_code >= 400:
            raise StorageError("Impossible de générer le lien de lecture.")
        signed = response.json().get("signedURL", "")
        return f"{self._base}{signed}" if signed.startswith("/") else signed

    async def download(self, object_key: str) -> bytes:
        async with self._client() as client:
            response = await client.get(f"{self._base}/object/{self._bucket}/{object_key}")
        if response.status_code == 404:
            raise StorageError(f"Objet introuvable : {object_key}")
        if response.status_code >= 400:
            raise StorageError("Échec du téléchargement de l'audio.")
        return response.content

    async def delete(self, object_key: str) -> None:
        async with self._client() as client:
            response = await client.delete(f"{self._base}/object/{self._bucket}/{object_key}")
        if response.status_code >= 400 and response.status_code != 404:
            raise StorageError("Échec de la suppression de l'objet.")

    async def exists(self, object_key: str) -> bool:
        async with self._client() as client:
            response = await client.head(f"{self._base}/object/{self._bucket}/{object_key}")
        return response.status_code < 400
