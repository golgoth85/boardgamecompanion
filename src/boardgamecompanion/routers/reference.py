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
from boardgamecompanion.catalog import explore_fact_match, explore_facts
from boardgamecompanion.description_translation import (
    DescriptionTranslationError,
    ReferenceDescriptionTranslationService,
)
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
    item_type: Literal["standalone", "expansion"] | None = Query(default=None),
    supports_players: int | None = Query(default=None, ge=1, le=30),
    ideal_players: int | None = Query(default=None, ge=1, le=30),
    player_age: int | None = Query(default=None, ge=3, le=99),
    weight: Literal["light", "medium", "heavy"] | None = Query(default=None),
    max_minutes: int | None = Query(default=None, ge=1, le=1440),
    min_rating: float | None = Query(default=None, ge=0, le=10),
    language: int | None = Query(default=None, ge=1, le=4),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    reference = BggReferenceCatalog(database)
    # Same parameters as the Ludoteca advanced search, evaluated like Esplora.
    filters = {
        key: value
        for key, value in {
            "supports_players": supports_players,
            "ideal_players": ideal_players,
            "player_age": player_age,
            "weight": weight,
            "max_minutes": max_minutes,
            "min_rating": min_rating,
            "language": language,
        }.items()
        if value is not None
    }
    allowed_ids = None
    if filters:
        allowed_ids = {
            int(row["bgg_id"])
            for row, facts in reference_row_facts(reference.explore_rows())
            if all(explore_fact_match(facts, key, value) for key, value in filters.items())
        }
    payload = reference.browse(
        query=q, sort=sort, limit=limit, offset=offset, item_type=item_type,
        allowed_ids=allowed_ids,
    )
    return {**payload, "filters": filters}


_facts_cache: dict[str, object] = {}


def reference_row_facts(rows: list[dict[str, object]]) -> list[tuple[dict[str, object], dict[str, object]]]:
    """Facts of the cached explore rows, computed once per scan."""
    if _facts_cache.get("rows") is not rows:
        _facts_cache["facts"] = [(row, explore_facts(row, str(row["name"]))) for row in rows]
        _facts_cache["rows"] = rows
    return _facts_cache["facts"]  # type: ignore[return-value]


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


def _reference_translation_service() -> ReferenceDescriptionTranslationService:
    database = get_database()
    database.initialize()
    return ReferenceDescriptionTranslationService(database)


def _translation_http_error(exc: DescriptionTranslationError) -> HTTPException:
    detail = str(exc)
    if "not found" in detail:
        code = 404
    elif "No BGG description" in detail:
        code = 409
    else:
        code = 503
    return HTTPException(status_code=code, detail=detail)


@router.get("/api/reference/{bgg_id:int}/description-it")
def reference_description_it(bgg_id: int) -> dict[str, object]:
    try:
        return _reference_translation_service().status(bgg_id)
    except DescriptionTranslationError as exc:
        raise _translation_http_error(exc) from exc


@router.post("/api/reference/{bgg_id:int}/description-it/translate")
def reference_translate_description_it(bgg_id: int) -> dict[str, object]:
    try:
        return _reference_translation_service().translate(bgg_id)
    except DescriptionTranslationError as exc:
        raise _translation_http_error(exc) from exc


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
