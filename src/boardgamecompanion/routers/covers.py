from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse

from boardgamecompanion.covers import CoverStore
from boardgamecompanion.dependencies import get_database
from boardgamecompanion.settings import settings

router = APIRouter(tags=["covers"])

IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


@router.get("/api/covers/{bgg_id}")
async def get_cover(bgg_id: int):
    with get_database().connect() as connection:
        row = connection.execute(
            """SELECT e.cover_url FROM board_game_enrichments e
               JOIN board_games g ON g.id=e.board_game_id
               WHERE g.bgg_id=?""",
            (bgg_id,),
        ).fetchone()
    url = row["cover_url"] if row else None
    if not url:
        raise HTTPException(status_code=404, detail="Cover non disponibile")
    path = await run_in_threadpool(CoverStore(settings.covers_dir).fetch, bgg_id, url)
    if path is None:
        if not CoverStore.url_allowed(url):
            raise HTTPException(status_code=404, detail="Cover non disponibile")
        # Archivio non montato o download fallito: ripiega sull'URL remoto.
        return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    return FileResponse(path, headers=IMMUTABLE)
