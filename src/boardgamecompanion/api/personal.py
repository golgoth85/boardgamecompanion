from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from boardgamecompanion.api.common import database
from boardgamecompanion.personal import PersonalGameError, PersonalGameService


router = APIRouter(prefix="/api", tags=["personal"])


class PersonalGamePayload(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    played: bool | None = None
    played_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.get("/games/{bgg_id}/personal")
def get_personal_game_state(bgg_id: int):
    try:
        return PersonalGameService(database()).get(bgg_id)
    except PersonalGameError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/games/{bgg_id}/personal")
def update_personal_game_state(bgg_id: int, payload: PersonalGamePayload):
    service = PersonalGameService(database())
    kwargs = {}
    fields = payload.model_fields_set
    if "rating" in fields:
        kwargs["rating"] = payload.rating
    if "played" in fields:
        kwargs["played"] = payload.played
    if "played_at" in fields:
        kwargs["played_at"] = payload.played_at
    try:
        return service.update(bgg_id, **kwargs)
    except PersonalGameError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
