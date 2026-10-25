from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse

from boardgamecompanion.covers import CoverStore
from boardgamecompanion.dependencies import get_database
from boardgamecompanion.settings import settings

router = APIRouter(tags=["covers"])

IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def _cover_url(bgg_id: int, variant: str) -> str | None:
    with get_database().connect() as connection:
        enriched = connection.execute(
            """SELECT e.cover_url FROM board_game_enrichments e
               JOIN board_games g ON g.id=e.board_game_id
               WHERE g.bgg_id=?""",
            (bgg_id,),
        ).fetchone()
        reference = connection.execute(
            "SELECT thumbnail_url,image_url FROM bgg_reference_games WHERE bgg_id=?",
            (bgg_id,),
        ).fetchone()
    own = enriched["cover_url"] if enriched else None
    image = reference["image_url"] if reference else None
    thumb = reference["thumbnail_url"] if reference else None
    candidates = (thumb, image, own) if variant == "thumb" else (own, image, thumb)
    return next((url for url in candidates if url), None)


@router.get("/api/covers/{bgg_id}")
async def get_cover(bgg_id: int, variant: str = Query("full", pattern="^(full|thumb)$")):
    url = await run_in_threadpool(_cover_url, bgg_id, variant)
    if not url or not CoverStore.url_allowed(url):
        raise HTTPException(status_code=404, detail="Cover non disponibile")
    path = await run_in_threadpool(CoverStore(settings.covers_dir).fetch, bgg_id, url)
    if path is None:
        # Archivio non montato o download fallito: ripiega sull'URL remoto.
        return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    return FileResponse(path, headers=IMMUTABLE)
