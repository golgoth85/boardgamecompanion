from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from boardgamecompanion.api.common import database
from boardgamecompanion.game_lists import GameListError, GameListService


router = APIRouter(prefix="/api/lists", tags=["lists"])


class CreateListPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["dynamic", "manual"]
    filters: dict[str, Any] = Field(default_factory=dict)


class UpdateListPayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    filters: dict[str, Any] | None = None


class ListGamePayload(BaseModel):
    bgg_id: int = Field(gt=0)


def _error(exc: GameListError) -> HTTPException:
    return HTTPException(
        status_code=404 if "not found" in str(exc).lower() else 400,
        detail=str(exc),
    )


@router.get("")
def list_game_lists():
    return {"items": GameListService(database()).list_all()}


@router.post("", status_code=201)
def create_game_list(payload: CreateListPayload):
    try:
        return GameListService(database()).create(
            name=payload.name,
            kind=payload.kind,
            filters=payload.filters,
        )
    except GameListError as exc:
        raise _error(exc) from exc


@router.get("/{list_id}")
def get_game_list(list_id: str):
    try:
        return GameListService(database()).evaluate(list_id)
    except GameListError as exc:
        raise _error(exc) from exc


@router.patch("/{list_id}")
def update_game_list(list_id: str, payload: UpdateListPayload):
    try:
        return GameListService(database()).update(
            list_id,
            name=payload.name,
            filters=payload.filters,
        )
    except GameListError as exc:
        raise _error(exc) from exc


@router.delete("/{list_id}", status_code=204)
def delete_game_list(list_id: str):
    try:
        GameListService(database()).delete(list_id)
    except GameListError as exc:
        raise _error(exc) from exc
    return None


@router.post("/{list_id}/games")
def add_game_to_list(list_id: str, payload: ListGamePayload):
    try:
        return GameListService(database()).add_game(list_id, payload.bgg_id)
    except GameListError as exc:
        raise _error(exc) from exc


@router.delete("/{list_id}/games/{bgg_id}")
def remove_game_from_list(list_id: str, bgg_id: int):
    try:
        return GameListService(database()).remove_game(list_id, bgg_id)
    except GameListError as exc:
        raise _error(exc) from exc
