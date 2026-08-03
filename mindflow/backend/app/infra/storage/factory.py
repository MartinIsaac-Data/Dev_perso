"""Storage adapter selection — configuration, not code (ADR-030)."""

from __future__ import annotations

from app.config import Settings
from app.domain.ports import ObjectStoragePort


def build_storage(settings: Settings) -> ObjectStoragePort:
    if settings.storage_backend == "supabase":
        from app.infra.storage.supabase import SupabaseObjectStorage

        return SupabaseObjectStorage(
            base_url=settings.supabase_url,
            service_key=settings.supabase_service_key,
            bucket=settings.storage_bucket,
            ttl_seconds=settings.storage_signed_url_ttl_seconds,
        )

    from app.infra.storage.local import LocalObjectStorage

    return LocalObjectStorage(
        settings.storage_local_root,
        base_url="http://localhost:8000",
        # Local only: the signing secret is not a production credential because
        # this backend is refused outside local/test by Settings.
        secret=f"local-{settings.env}",
        ttl_seconds=settings.storage_signed_url_ttl_seconds,
    )
