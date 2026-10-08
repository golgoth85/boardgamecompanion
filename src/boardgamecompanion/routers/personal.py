from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from boardgamecompanion.dependencies import get_database
from boardgamecompanion.personal_state import (
    PersonalStateError,
    PersonalStateNotFound,
    PersonalStateStore,
    UNSET,
)

router = APIRouter(tags=["personal"])


class PersonalStatePayload(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    played: bool | None = None
    played_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    completed: bool | None = None
    completed_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.get("/api/games/{bgg_id}/personal-state")
def get_personal_state(bgg_id: int) -> dict[str, object]:
    try:
        return PersonalStateStore(get_database()).get(bgg_id)
    except PersonalStateNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/api/games/{bgg_id}/personal-state")
def update_personal_state(
    bgg_id: int,
    payload: PersonalStatePayload,
) -> dict[str, object]:
    values = payload.model_dump()
    fields = payload.model_fields_set
    try:
        return PersonalStateStore(get_database()).update(
            bgg_id,
            rating=values["rating"] if "rating" in fields else UNSET,
            played=values["played"] if "played" in fields else UNSET,
            played_at=values["played_at"] if "played_at" in fields else UNSET,
            completed=values["completed"] if "completed" in fields else UNSET,
            completed_at=values["completed_at"] if "completed_at" in fields else UNSET,
        )
    except PersonalStateNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersonalStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
