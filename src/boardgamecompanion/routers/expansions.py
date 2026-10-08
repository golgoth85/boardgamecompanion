from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from boardgamecompanion.expansions import ExpansionGameNotFound
from boardgamecompanion.service_factories import get_expansion_service

router = APIRouter(tags=["expansions"])


@router.get("/api/games/{bgg_id}/expansions")
def list_relevant_expansions(
    bgg_id: int,
    refresh: bool = Query(default=False),
) -> dict[str, object]:
    try:
        return get_expansion_service().list_for_game(
            bgg_id,
            refresh=refresh,
            fetch_details=True,
        )
    except ExpansionGameNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
