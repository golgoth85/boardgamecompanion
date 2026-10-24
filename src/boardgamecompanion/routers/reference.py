from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from boardgamecompanion.bgg_reference import (
    DUMP_DEFAULT_FILENAME,
    MIN_VOTES_RANGE,
    BggReferenceCatalog,
    BggReferenceError,
    BggReferenceImporter,
    ReferenceSettings,
    load_reference_settings,
    save_reference_settings,
)
from boardgamecompanion.dependencies import get_database
from boardgamecompanion.settings import settings

router = APIRouter(tags=["reference"])


class DumpImportPayload(BaseModel):
    filename: str = Field(default=DUMP_DEFAULT_FILENAME, min_length=1, max_length=255)


class ReferenceSettingsPayload(BaseModel):
    min_votes: int = Field(ge=MIN_VOTES_RANGE[0], le=MIN_VOTES_RANGE[1])
    include_expansions: bool = True


def _import_file(filename: str) -> Path:
    if Path(filename).name != filename or not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Expected a .csv file name in the import folder")
    path = settings.import_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{filename} not found in the import folder")
    return path


@router.get("/api/reference/status")
def reference_status() -> dict[str, object]:
    database = get_database()
    database.initialize()
    return BggReferenceCatalog(database).status()


@router.get("/api/reference/search")
def reference_search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    items = BggReferenceCatalog(database).search(q, limit=limit)
    return {"query": q, "items": items}


@router.post("/api/reference/import-dump")
def reference_import_dump(payload: DumpImportPayload | None = None) -> dict[str, object]:
    path = _import_file((payload or DumpImportPayload()).filename)
    database = get_database()
    database.initialize()
    try:
        result = BggReferenceImporter(database).import_path(path)
    except BggReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.to_dict()


@router.get("/api/reference/settings")
def reference_settings_get() -> dict[str, object]:
    database = get_database()
    database.initialize()
    return load_reference_settings(database).to_dict()


@router.put("/api/reference/settings")
def reference_settings_put(payload: ReferenceSettingsPayload) -> dict[str, object]:
    database = get_database()
    database.initialize()
    saved = save_reference_settings(
        database,
        ReferenceSettings(
            min_votes=payload.min_votes,
            include_expansions=payload.include_expansions,
        ),
    )
    return saved.to_dict()
