from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from boardgamecompanion.dependencies import get_database
from boardgamecompanion.plays import PlayError, PlayLog, PlayNotFound

router = APIRouter(tags=["plays"])

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class PlayerPayload(BaseModel):
    name: str = Field(default="", max_length=60)
    score: str | None = Field(default=None, max_length=20)
    winner: bool = False


class PlayPayload(BaseModel):
    played_on: str | None = Field(default=None, pattern=DATE_PATTERN)
    player_count: int | None = Field(default=None, ge=1, le=99)
    players: list[PlayerPayload] | None = Field(default=None, max_length=20)
    duration_minutes: int | None = Field(default=None, ge=1, le=10000)
    outcome: str | None = Field(default=None, pattern="^(won|lost|draw)$")
    activity: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=120)
    completed_game: bool | None = None

    def values(self) -> dict[str, Any]:
        data = self.model_dump(include=self.model_fields_set)
        if data.get("completed_game") is None:
            data.pop("completed_game", None)
        return data


def _log() -> PlayLog:
    return PlayLog(get_database())


def _call(function, *args):
    try:
        return function(*args)
    except PlayNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlayError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/plays")
def list_plays(
    bgg_id: int | None = Query(default=None, ge=1),
    player: str | None = Query(default=None, max_length=60),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    return _log().list(bgg_id=bgg_id, player=player, q=q, limit=limit, offset=offset)


@router.get("/api/plays/summary")
def plays_summary() -> dict[str, object]:
    return _log().summary()


@router.get("/api/plays/defaults")
def play_defaults(bgg_id: int | None = Query(default=None, ge=1)) -> dict[str, object]:
    return _log().defaults(bgg_id)


@router.post("/api/games/{bgg_id}/plays", status_code=201)
def create_play(bgg_id: int, payload: PlayPayload) -> dict[str, object]:
    return _call(_log().create, bgg_id, payload.values())


@router.patch("/api/plays/{play_id}")
def update_play(play_id: int, payload: PlayPayload) -> dict[str, object]:
    return _call(_log().update, play_id, payload.values())


@router.delete("/api/plays/{play_id}", status_code=204)
def delete_play(play_id: int) -> Response:
    _call(_log().delete, play_id)
    return Response(status_code=204)
