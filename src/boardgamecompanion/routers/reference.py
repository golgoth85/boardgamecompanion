from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from boardgamecompanion.bgg_reference import (
    DUMP_DEFAULT_FILENAME,
    DEFAULT_CROWDFUNDING_GRACE_DAYS,
    DEFAULT_DAILY_BUDGET,
    DEFAULT_MIN_WISHING,
    MAX_CROWDFUNDING_GRACE_DAYS,
    MAX_DAILY_BUDGET,
    MAX_MIN_WISHING,
    MIN_VOTES_MINIMUM,
    BggReferenceCatalog,
    BggReferenceError,
    BggReferenceImporter,
    ReferenceSettings,
    load_reference_settings,
    save_reference_settings,
)
from boardgamecompanion.bgg_reference_worker import worker_status
from boardgamecompanion.dependencies import get_database
from boardgamecompanion.service_factories import get_bgg_api_client
from boardgamecompanion.settings import settings

router = APIRouter(tags=["reference"])


class DumpImportPayload(BaseModel):
    filename: str = Field(default=DUMP_DEFAULT_FILENAME, min_length=1, max_length=255)


class ReferenceSettingsPayload(BaseModel):
    min_votes: int = Field(ge=MIN_VOTES_MINIMUM)
    include_expansions: bool = True
    min_wishing: int = Field(default=DEFAULT_MIN_WISHING, ge=0, le=MAX_MIN_WISHING)
    daily_budget: int = Field(default=DEFAULT_DAILY_BUDGET, ge=0, le=MAX_DAILY_BUDGET)
    crowdfunding_grace_days: int = Field(
        default=DEFAULT_CROWDFUNDING_GRACE_DAYS, ge=0, le=MAX_CROWDFUNDING_GRACE_DAYS
    )


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
    return {**BggReferenceCatalog(database).status(), "worker": worker_status(database)}


@router.get("/api/reference/search")
def reference_search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    items = BggReferenceCatalog(database).search(q, limit=limit)
    return {"query": q, "items": items}


@router.get("/api/reference/browse")
def reference_browse(
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["rank", "votes", "rating", "newest", "title"] = Query(default="rank"),
    limit: int = Query(default=48, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    return BggReferenceCatalog(database).browse(query=q, sort=sort, limit=limit, offset=offset)


@router.get("/api/reference/{bgg_id:int}")
def reference_detail(bgg_id: int) -> dict[str, object]:
    database = get_database()
    database.initialize()
    catalog = BggReferenceCatalog(database)
    # The existing row answers immediately; a single /thing is fetched only the
    # first time the user opens a title that was never queried.
    item = catalog.detail(bgg_id, get_bgg_api_client())
    if item is None:
        raise HTTPException(status_code=404, detail=f"BGG #{bgg_id} is not in the reference catalog")
    return item


@router.post("/api/reference/{bgg_id:int}/collection", status_code=201)
def reference_add_to_collection(bgg_id: int) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        return BggReferenceCatalog(database).add_to_collection(bgg_id)
    except BggReferenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
            min_wishing=payload.min_wishing,
            daily_budget=payload.daily_budget,
            crowdfunding_grace_days=payload.crowdfunding_grace_days,
        ),
    )
    return saved.to_dict()
