from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from boardgamecompanion.dependencies import get_database
from boardgamecompanion.players import PlayerError, PlayerNotFound, PlayerProfiles
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
    session_duration_minutes: int | None = Field(default=None, ge=1, le=10000)
    outcome: str | None = Field(default=None, pattern="^(won|lost|draw)$")
    play_mode: str | None = Field(default=None, pattern="^(competitive|cooperative)$")
    activity: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=120)
    completed_game: bool | None = None

    def values(self) -> dict[str, Any]:
        data = self.model_dump(include=self.model_fields_set)
        if data.get("completed_game") is None:
            data.pop("completed_game", None)
        return data


class SessionRoundPayload(BaseModel):
    winner_indices: list[int] = Field(default_factory=list, max_length=20)
    scores: list[str | None] | None = Field(default=None, max_length=20)
    outcome: str | None = Field(default=None, pattern="^(won|lost|draw)$")


class PlaySessionPayload(PlayPayload):
    request_id: str = Field(pattern="^[a-f0-9]{32}$")
    rounds: list[SessionRoundPayload] = Field(min_length=2, max_length=20)


def _log() -> PlayLog:
    return PlayLog(get_database())


def _profiles() -> PlayerProfiles:
    return PlayerProfiles(get_database())


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (PlayNotFound, PlayerNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PlayError, PlayerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PlayerProfilePayload(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    aliases: list[str] | None = Field(default=None, max_length=10)
    description: str | None = Field(default=None, max_length=1000)
    color: str | None = Field(default=None, pattern="^#[0-9a-f]{6}$")

    def values(self) -> dict[str, Any]:
        return self.model_dump(include=self.model_fields_set)


class PlayerPhotoPayload(BaseModel):
    data_url: str = Field(max_length=900_000)


@router.get("/api/plays")
def list_plays(
    bgg_id: int | None = Query(default=None, ge=1),
    player: str | None = Query(default=None, max_length=60),
    q: str | None = Query(default=None, max_length=100),
    player_id: int | None = Query(default=None, ge=1),
    date_from: str | None = Query(default=None, pattern=DATE_PATTERN),
    date_to: str | None = Query(default=None, pattern=DATE_PATTERN),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    before_date: str | None = Query(default=None, pattern=DATE_PATTERN),
    before_id: int | None = Query(default=None, ge=1),
) -> dict[str, object]:
    if (before_date is None) != (before_id is None) or (before_date is not None and offset):
        raise HTTPException(status_code=400, detail="Specify both cursor fields or use offset")
    before = (before_date, before_id) if before_date is not None and before_id is not None else None
    return _log().list(bgg_id=bgg_id, player=player, q=q, player_id=player_id,
                       date_from=date_from, date_to=date_to, limit=limit, offset=offset, before=before)


@router.get("/api/plays/summary")
def plays_summary() -> dict[str, object]:
    return _log().summary()


@router.get("/api/plays/stats")
def plays_stats(
    period: str = Query(default="month", pattern="^(day|week|month|year|all)$"),
    anchor: str | None = Query(default=None, pattern=DATE_PATTERN),
    player_id: int | None = Query(default=None, ge=1),
    player: str | None = Query(default=None, max_length=60),
) -> dict[str, object]:
    return _call(_log().stats, period=period, anchor=anchor, player_id=player_id, player=player)


@router.get("/api/players")
def list_players() -> dict[str, object]:
    return {"items": _profiles().list()}


@router.post("/api/players", status_code=201)
def create_player(payload: PlayerProfilePayload) -> dict[str, object]:
    return _call(_profiles().create, payload.values())


@router.get("/api/players/{player_id}")
def player_overview(player_id: int) -> dict[str, object]:
    return _call(_log().player_overview, player_id)


@router.patch("/api/players/{player_id}")
def update_player(player_id: int, payload: PlayerProfilePayload) -> dict[str, object]:
    return _call(_profiles().update, player_id, payload.values())


@router.delete("/api/players/{player_id}", status_code=204)
def delete_player(player_id: int) -> Response:
    _call(_profiles().delete, player_id)
    return Response(status_code=204)


@router.put("/api/players/{player_id}/photo")
def set_player_photo(player_id: int, payload: PlayerPhotoPayload) -> dict[str, object]:
    return _call(_profiles().set_photo, player_id, payload.data_url)


@router.delete("/api/players/{player_id}/photo")
def clear_player_photo(player_id: int) -> dict[str, object]:
    return _call(_profiles().clear_photo, player_id)


@router.get("/api/players/{player_id}/photo")
def player_photo(player_id: int) -> Response:
    content, media_type = _call(_profiles().photo, player_id)
    # L'indirizzo cambia a ogni nuova foto (?v=...), quindi la cache può essere lunga.
    return Response(content=content, media_type=media_type,
                    headers={"Cache-Control": "private, max-age=31536000, immutable",
                             "X-Content-Type-Options": "nosniff"})


@router.get("/api/plays/defaults")
def play_defaults(bgg_id: int | None = Query(default=None, ge=1)) -> dict[str, object]:
    return _log().defaults(bgg_id)


@router.post("/api/games/{bgg_id}/plays", status_code=201)
def create_play(bgg_id: int, payload: PlayPayload) -> dict[str, object]:
    return _call(_log().create, bgg_id, payload.values())


@router.patch("/api/plays/{play_id}")
def update_play(play_id: int, payload: PlayPayload) -> dict[str, object]:
    return _call(_log().update, play_id, payload.values())


@router.post("/api/games/{bgg_id}/play-sessions", status_code=201)
def create_session(bgg_id: int, payload: PlaySessionPayload) -> dict[str, object]:
    # I default delle righe fanno parte del contenuto idempotente della richiesta.
    values = payload.values()
    values["rounds"] = [item.model_dump() for item in payload.rounds]
    return _call(_log().create_session, bgg_id, values)


@router.delete("/api/plays/{play_id}", status_code=204)
def delete_play(play_id: int) -> Response:
    _call(_log().delete, play_id)
    return Response(status_code=204)
