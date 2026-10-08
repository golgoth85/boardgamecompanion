from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from boardgamecompanion.dependencies import get_database
from boardgamecompanion.game_lists import GameListError, GameListNotFound, GameListStore

router = APIRouter(tags=["lists"])


class GameListCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["smart", "manual"]
    filters: dict[str, Any] = Field(default_factory=dict)


class GameListUpdatePayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    filters: dict[str, Any] | None = None


@router.get("/api/lists")
def list_game_lists() -> dict[str, object]:
    items = GameListStore(get_database()).list()
    return {"items": items, "total": len(items)}


@router.post("/api/lists", status_code=201)
def create_game_list(payload: GameListCreatePayload) -> dict[str, object]:
    try:
        return GameListStore(get_database()).create(**payload.model_dump())
    except GameListError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/lists/{list_id}")
def get_game_list(list_id: str) -> dict[str, object]:
    try:
        return GameListStore(get_database()).get(list_id)
    except GameListNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/api/lists/{list_id}")
def update_game_list(
    list_id: str,
    payload: GameListUpdatePayload,
) -> dict[str, object]:
    try:
        return GameListStore(get_database()).update(
            list_id,
            **payload.model_dump(exclude_unset=True),
        )
    except GameListNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GameListError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game_list(list_id: str) -> Response:
    try:
        GameListStore(get_database()).delete(list_id)
    except GameListNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/lists/{list_id}/games")
def resolve_game_list(
    list_id: str,
    limit: int = Query(default=250, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    try:
        return GameListStore(get_database()).resolve(
            list_id,
            limit=limit,
            offset=offset,
        )
    except GameListNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GameListError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/lists/{list_id}/items/{bgg_id}", status_code=204)
def add_manual_list_item(list_id: str, bgg_id: int) -> Response:
    try:
        GameListStore(get_database()).set_manual_item(list_id, bgg_id, present=True)
    except GameListNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GameListError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)


@router.delete("/api/lists/{list_id}/items/{bgg_id}", status_code=204)
def remove_manual_list_item(list_id: str, bgg_id: int) -> Response:
    try:
        GameListStore(get_database()).set_manual_item(list_id, bgg_id, present=False)
    except GameListNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GameListError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)
