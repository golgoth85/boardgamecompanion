from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from boardgamecompanion.api.common import database
from boardgamecompanion.app_settings import resolve_bgg_settings
from boardgamecompanion.bgg_metadata import BggApiClient, BggApiConfig, BggMetadataError
from boardgamecompanion.expansions import ExpansionService
from boardgamecompanion.rate_limits import PersistentRateLimiter


router = APIRouter(prefix="/api/games", tags=["catalog"])


def expansion_service() -> ExpansionService:
    db = database()
    resolved = resolve_bgg_settings(db)
    token = (resolved.application_token or "").strip()
    client = None
    if token:
        client = BggApiClient(
            BggApiConfig(
                application_token=token,
                timeout_seconds=resolved.timeout_seconds,
                min_interval_seconds=resolved.min_interval_seconds,
            ),
            rate_limiter=PersistentRateLimiter(db).acquire,
        )
    return ExpansionService(db, client)


@router.get("/{bgg_id}/expansions")
def game_expansions(
    bgg_id: int,
    refresh: bool = Query(default=False),
):
    try:
        service = expansion_service()
        cached = service.cached(bgg_id)
        if refresh or not cached["items"]:
            return service.refresh(bgg_id, force=refresh)
        return cached
    except BggMetadataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=404 if "not found" in str(exc).lower() else 400,
            detail=str(exc),
        ) from exc
