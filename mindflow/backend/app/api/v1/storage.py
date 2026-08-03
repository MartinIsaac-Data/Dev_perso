"""Local development object endpoint.

Only mounted when `storage_backend == "local"`. It exists so the client follows
the *same* signed-URL flow locally as in production (ADR-018/030) — otherwise the
production upload path would only ever be exercised by hand.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import SettingsDep
from app.domain.errors import ForbiddenError, StorageError
from app.infra.storage.factory import build_storage
from app.infra.storage.local import LocalObjectStorage

router = APIRouter(prefix="/storage", include_in_schema=False)


def _local(settings) -> LocalObjectStorage:  # type: ignore[no-untyped-def]
    storage = build_storage(settings)
    if not isinstance(storage, LocalObjectStorage):
        raise StorageError("Endpoint disponible uniquement avec le stockage local.")
    return storage


@router.put("/{object_key:path}", status_code=status.HTTP_204_NO_CONTENT)
async def put_object(
    object_key: str,
    request: Request,
    settings: SettingsDep,
    expires: int = Query(...),
    signature: str = Query(...),
) -> None:
    storage = _local(settings)
    if not storage.verify(object_key, expires, signature):
        raise ForbiddenError("Signature d'envoi invalide ou expirée.")
    body = await request.body()
    if len(body) > settings.storage_max_audio_bytes:
        raise StorageError("Fichier trop volumineux.")
    await storage.put(object_key, body)


@router.get("/{object_key:path}")
async def get_object(
    object_key: str,
    settings: SettingsDep,
    expires: int = Query(...),
    signature: str = Query(...),
) -> Response:
    storage = _local(settings)
    if not storage.verify(object_key, expires, signature):
        raise ForbiddenError("Signature de lecture invalide ou expirée.")
    data = await storage.download(object_key)
    media = {
        "m4a": "audio/mp4",
        "opus": "audio/ogg",
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "webm": "audio/webm",
    }.get(object_key.rsplit(".", 1)[-1], "application/octet-stream")
    return Response(content=data, media_type=media)
