import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from boardgamecompanion import __version__
from boardgamecompanion.app_settings import (
    resolve_floppy_settings,
    save_floppy_settings,
)
from boardgamecompanion.bgg_csv import BggCsvError, BggCsvImporter
from boardgamecompanion.catalog import SORT_SQL, Catalog
from boardgamecompanion.copies import (
    BoardGameNotFound,
    PhysicalCopyError,
    PhysicalCopyNotFound,
    PhysicalCopyStore,
)
from boardgamecompanion.database import Database
from boardgamecompanion.documents import (
    BoardGameDocumentNotFound,
    DocumentError,
    DocumentNotFound,
    DocumentStore,
    DocumentTooLarge,
    InvalidPdf,
)
from boardgamecompanion.floppy import (
    FloppyClient,
    FloppyConfig,
    FloppyError,
    FloppyPlanChanged,
    apply_floppy_sync,
    build_sync_preview,
    load_floppy_links,
    local_owned_games,
    reconcile_floppy_links,
)
from boardgamecompanion.metadata import (
    GameMetadataError,
    GameMetadataGameNotFound,
    GameMetadataStore,
)
from boardgamecompanion.rulebook_review import (
    RulebookReviewConflict,
    RulebookReviewCorruptRecord,
    RulebookReviewError,
    RulebookReviewNotFound,
    RulebookReviewQueue,
)
from boardgamecompanion.rulebook_updates import (
    MAX_INTERVAL_SECONDS,
    MIN_INTERVAL_SECONDS,
    RulebookUpdateBusy,
    RulebookUpdateConflict,
    RulebookUpdateError,
    RulebookUpdateNotApproved,
    RulebookUpdateNotFound,
    RulebookUpdateService,
)
from boardgamecompanion.settings import settings

WEB_DIR = Path(__file__).parent / "web"
LOGGER = logging.getLogger(__name__)


def get_database() -> Database:
    return Database(settings.database_path)


def get_rulebook_update_service() -> RulebookUpdateService:
    database = get_database()
    database.initialize()
    return RulebookUpdateService(
        database,
        settings.manuals_dir,
        default_interval_seconds=settings.rulebook_update_default_interval_seconds,
        retry_base_seconds=settings.rulebook_update_retry_base_seconds,
        retry_max_seconds=settings.rulebook_update_retry_max_seconds,
        lease_seconds=settings.rulebook_update_lease_seconds,
        max_archive_bytes=settings.max_document_bytes,
        fetch_max_bytes=settings.rulebook_fetch_max_bytes,
    )


def get_floppy_client() -> FloppyClient | None:
    database = get_database()
    database.initialize()
    resolved = resolve_floppy_settings(database)
    if not resolved.configured:
        return None
    return FloppyClient(
        FloppyConfig(
            base_url=resolved.url or "",
            api_key=resolved.api_key or "",
            timeout_seconds=resolved.timeout_seconds,
            verify_tls=resolved.verify_tls,
        )
    )


def floppy_http_error(exc: FloppyError) -> HTTPException:
    if exc.kind == "authentication":
        return HTTPException(status_code=502, detail="Floppy authentication failed")
    if exc.kind in {"timeout", "unreachable"}:
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


def rulebook_update_http_error(exc: RulebookUpdateError) -> HTTPException:
    if isinstance(exc, RulebookUpdateNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc,
        (RulebookUpdateBusy, RulebookUpdateConflict, RulebookUpdateNotApproved),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


class PhysicalCopyPayload(BaseModel):
    barcode: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=500)
    edition: str | None = Field(default=None, max_length=500)
    publishers: str | None = Field(default=None, max_length=1000)
    version_year_published: int | None = Field(default=None, ge=1000, le=3000)
    acquisition_date: str | None = Field(default=None, max_length=64)
    acquired_from: str | None = Field(default=None, max_length=500)
    price_paid: float | None = Field(default=None, ge=0)
    price_currency: str | None = Field(default=None, max_length=16)
    condition_text: str | None = Field(default=None, max_length=500)
    inventory_location: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)


class BarcodeLookupRequest(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)


class FloppySyncRequest(BaseModel):
    plan_hash: str = Field(min_length=64, max_length=64)
    batch_size: int = Field(default=20, ge=1, le=50)


class FloppySettingsUpdate(BaseModel):
    url: str = ""
    api_key: str | None = None
    clear_api_key: bool = False
    timeout_seconds: float = Field(default=45.0, ge=1.0, le=60.0)
    verify_tls: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("Floppy URL must start with http:// or https://")
        return value


class RulebookReviewDecisionPayload(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


class RulebookUpdateSchedulePayload(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = Field(
        default=None,
        ge=MIN_INTERVAL_SECONDS,
        le=MAX_INTERVAL_SECONDS,
    )


async def _rulebook_update_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.rulebook_update_poll_seconds,
            )
            break
        except TimeoutError:
            pass

        try:
            service = get_rulebook_update_service()
            await asyncio.to_thread(
                service.run_due,
                limit=settings.rulebook_update_batch_size,
            )
        except Exception:
            LOGGER.exception("Scheduled rulebook update worker failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    get_database().initialize()

    worker_task: asyncio.Task[None] | None = None
    worker_stop: asyncio.Event | None = None
    if settings.rulebook_update_worker_enabled:
        try:
            await asyncio.to_thread(
                get_rulebook_update_service().synchronize_approved_targets
            )
        except Exception:
            LOGGER.exception(
                "Initial rulebook update target synchronization failed"
            )
        worker_stop = asyncio.Event()
        worker_task = asyncio.create_task(
            _rulebook_update_worker(worker_stop)
        )

    try:
        yield
    finally:
        if worker_task is not None and worker_stop is not None:
            worker_stop.set()
            await worker_task


app = FastAPI(
    title="BoardGameCompanion",
    version=__version__,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def web_home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/games/{bgg_id}", include_in_schema=False)
def web_game(bgg_id: int) -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/reviews", include_in_schema=False)
def web_reviews() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/updates", include_in_schema=False)
def web_updates() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health", tags=["system"])
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "storage": {
            "config": str(settings.config_dir),
            "import": str(settings.import_dir),
            "manuals": str(settings.manuals_dir),
            "database": str(settings.database_path),
        },
    }


@app.post("/api/imports/bgg-csv", tags=["imports"])
async def import_bgg_csv(file: UploadFile = File(...)) -> dict[str, object]:
    filename = Path(file.filename or "collection.csv").name
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Expected a .csv file")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")

    database = get_database()
    database.initialize()
    importer = BggCsvImporter(database)

    try:
        result = importer.import_bytes(payload, filename)
    except BggCsvError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    snapshot_name = f"{result.sha256[:12]}-{filename}"
    snapshot_path = settings.import_dir / snapshot_name
    if not snapshot_path.exists():
        snapshot_path.write_bytes(payload)

    return {**result.to_dict(), "snapshot": str(snapshot_path)}


@app.get("/api/games", tags=["catalog"])
def list_games(
    q: str | None = Query(default=None, min_length=1),
    item_type: str | None = Query(default=None),
    owned: bool | None = Query(default=None),
    sort: str = Query(default="title"),
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    return Catalog(database).list_games(
        query=q,
        item_type=item_type,
        owned=owned,
        sort=sort if sort in SORT_SQL else "title",
        limit=limit,
        offset=offset,
    )


@app.get("/api/games/{bgg_id}", tags=["catalog"])
def get_game(bgg_id: int) -> dict[str, object]:
    database = get_database()
    database.initialize()
    game = Catalog(database).get_game(bgg_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Board game not found")
    return game


@app.post("/api/games/{bgg_id}/metadata/refresh", tags=["catalog"])
def refresh_game_metadata(bgg_id: int) -> dict[str, object]:
    database = get_database()
    database.initialize()
    if Catalog(database).get_game(bgg_id) is None:
        raise HTTPException(status_code=404, detail="Board game not found")

    client = get_floppy_client()
    if client is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Floppy is not configured. Open Impostazioni and configure "
                "URL and API token."
            ),
        )

    try:
        provider_payload = client.boardgame_bgg_provider_detail(bgg_id)
    except FloppyError as exc:
        raise floppy_http_error(exc) from exc

    if provider_payload is None:
        raise HTTPException(
            status_code=404,
            detail="BGG metadata was not found through Floppy",
        )

    try:
        metadata, changed = GameMetadataStore(database).upsert_from_floppy(
            bgg_id,
            provider_payload,
        )
    except GameMetadataGameNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GameMetadataError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Invalid BGG metadata returned through Floppy: {exc}",
        ) from exc

    return {
        "bgg_id": bgg_id,
        "changed": changed,
        "metadata": metadata,
    }


@app.get("/api/games/{bgg_id}/copies", tags=["copies"])
def list_physical_copies(bgg_id: int) -> dict[str, object]:
    database = get_database()
    database.initialize()
    copies = PhysicalCopyStore(database).list_for_game(bgg_id)
    return {"bgg_id": bgg_id, "count": len(copies), "items": copies}


@app.post("/api/games/{bgg_id}/copies", tags=["copies"], status_code=201)
def create_physical_copy(
    bgg_id: int,
    payload: PhysicalCopyPayload,
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        return PhysicalCopyStore(database).create(
            bgg_id,
            payload.model_dump(exclude_unset=True),
        )
    except BoardGameNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PhysicalCopyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/copies/{copy_id}", tags=["copies"])
def update_physical_copy(
    copy_id: str,
    payload: PhysicalCopyPayload,
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        return PhysicalCopyStore(database).update(
            copy_id,
            payload.model_dump(exclude_unset=True),
        )
    except PhysicalCopyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PhysicalCopyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/barcodes/lookup", tags=["copies"])
def lookup_barcode(payload: BarcodeLookupRequest) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        return PhysicalCopyStore(database).lookup_barcode(payload.barcode)
    except PhysicalCopyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/games/{bgg_id}/documents", tags=["documents"])
def list_game_documents(bgg_id: int) -> dict[str, object]:
    database = get_database()
    database.initialize()
    documents = DocumentStore(database, settings.manuals_dir).list_for_game(bgg_id)
    return {"bgg_id": bgg_id, "count": len(documents), "items": documents}


@app.post("/api/games/{bgg_id}/documents", tags=["documents"])
def upload_game_document(
    bgg_id: int,
    file: UploadFile = File(...),
    document_type: str = Form("rulebook"),
    language: str = Form("und"),
    title: str | None = Form(None),
    version_label: str | None = Form(None),
    edition: str | None = Form(None),
    published_at: str | None = Form(None),
    source_url: str | None = Form(None),
    is_official: bool = Form(False),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    store = DocumentStore(database, settings.manuals_dir)

    try:
        file.file.seek(0)
        document, created = store.import_pdf(
            bgg_id=bgg_id,
            original_filename=file.filename or "document.pdf",
            stream=file.file,
            document_type=document_type,
            language=language,
            title=title,
            version_label=version_label,
            edition=edition,
            published_at=published_at,
            source_url=source_url,
            is_official=is_official,
            max_bytes=settings.max_document_bytes,
        )
    except BoardGameDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (InvalidPdf, DocumentError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"created": created, "document": document}


@app.get("/api/documents/{document_id}", tags=["documents"])
def get_document(document_id: str) -> dict[str, object]:
    database = get_database()
    database.initialize()
    document = DocumentStore(database, settings.manuals_dir).get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.get("/api/documents/{document_id}/file", tags=["documents"])
def get_document_file(document_id: str) -> FileResponse:
    database = get_database()
    database.initialize()
    store = DocumentStore(database, settings.manuals_dir)
    try:
        path = store.resolve_path(document_id)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/pdf")


@app.get("/api/rulebook-reviews", tags=["rulebooks"])
def list_rulebook_reviews(
    status: str | None = Query(default=None),
    bgg_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        return RulebookReviewQueue(database).list(
            status=status,
            bgg_id=bgg_id,
            limit=limit,
            offset=offset,
        )
    except RulebookReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/rulebook-reviews/{review_id}", tags=["rulebooks"])
def get_rulebook_review(review_id: str) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        item = RulebookReviewQueue(database).get(review_id)
    except RulebookReviewCorruptRecord as exc:
        raise HTTPException(
            status_code=500,
            detail="Rulebook review contains corrupt persisted data",
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Rulebook review not found")
    return item


@app.post("/api/rulebook-reviews/{review_id}/decision", tags=["rulebooks"])
def decide_rulebook_review(
    review_id: str,
    payload: RulebookReviewDecisionPayload,
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        item = RulebookReviewQueue(database).decide(
            review_id,
            decision=payload.decision,
            note=payload.note,
        )
        if item["status"] == "approved":
            get_rulebook_update_service().ensure_target(review_id)
        return item
    except RulebookReviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RulebookReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RulebookReviewCorruptRecord as exc:
        raise HTTPException(
            status_code=500,
            detail="Rulebook review contains corrupt persisted data",
        ) from exc
    except RulebookReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RulebookUpdateError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Review approved but update scheduling failed: {exc}",
        ) from exc


@app.get("/api/rulebook-updates", tags=["rulebooks"])
def list_rulebook_updates(
    enabled: bool | None = Query(default=None),
    bgg_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    service = get_rulebook_update_service()
    service.synchronize_approved_targets(limit=500)
    payload = service.list_targets(
        enabled=enabled,
        bgg_id=bgg_id,
        limit=limit,
        offset=offset,
    )
    payload["worker"] = {
        "enabled": settings.rulebook_update_worker_enabled,
        "poll_seconds": settings.rulebook_update_poll_seconds,
        "batch_size": settings.rulebook_update_batch_size,
    }
    return payload


@app.get("/api/rulebook-updates/{review_id}", tags=["rulebooks"])
def get_rulebook_update(review_id: str) -> dict[str, object]:
    service = get_rulebook_update_service()
    try:
        target = service.get_target(review_id)
    except RulebookReviewCorruptRecord as exc:
        raise HTTPException(
            status_code=500,
            detail="Rulebook update target references corrupt review data",
        ) from exc
    if target is None:
        raise HTTPException(status_code=404, detail="Rulebook update target not found")
    return target


@app.patch("/api/rulebook-updates/{review_id}", tags=["rulebooks"])
def configure_rulebook_update(
    review_id: str,
    payload: RulebookUpdateSchedulePayload,
) -> dict[str, object]:
    try:
        return get_rulebook_update_service().configure_target(
            review_id,
            enabled=payload.enabled,
            interval_seconds=payload.interval_seconds,
        )
    except RulebookReviewCorruptRecord as exc:
        raise HTTPException(
            status_code=500,
            detail="Rulebook review contains corrupt persisted data",
        ) from exc
    except RulebookUpdateError as exc:
        raise rulebook_update_http_error(exc) from exc


@app.post("/api/rulebook-updates/{review_id}/run", tags=["rulebooks"])
def run_rulebook_update_now(review_id: str) -> dict[str, object]:
    try:
        return get_rulebook_update_service().run_review_now(review_id)
    except RulebookReviewCorruptRecord as exc:
        raise HTTPException(
            status_code=500,
            detail="Rulebook review contains corrupt persisted data",
        ) from exc
    except RulebookUpdateError as exc:
        raise rulebook_update_http_error(exc) from exc


@app.get("/api/rulebook-updates/{review_id}/runs", tags=["rulebooks"])
def list_rulebook_update_runs(
    review_id: str,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    try:
        return get_rulebook_update_service().list_runs(
            review_id,
            limit=limit,
            offset=offset,
        )
    except RulebookUpdateError as exc:
        raise rulebook_update_http_error(exc) from exc


@app.get("/api/catalog/stats", tags=["catalog"])
def catalog_stats() -> dict[str, int]:
    database = get_database()
    database.initialize()
    return Catalog(database).stats()


@app.get("/api/settings/floppy", tags=["settings"])
def get_floppy_settings() -> dict[str, object]:
    database = get_database()
    database.initialize()
    return resolve_floppy_settings(database).public_dict()


@app.put("/api/settings/floppy", tags=["settings"])
def update_floppy_settings(payload: FloppySettingsUpdate) -> dict[str, object]:
    database = get_database()
    database.initialize()
    resolved = save_floppy_settings(
        database,
        url=payload.url,
        api_key=payload.api_key,
        clear_api_key=payload.clear_api_key,
        timeout_seconds=payload.timeout_seconds,
        verify_tls=payload.verify_tls,
    )
    return resolved.public_dict()


@app.get("/api/integrations/floppy/status", tags=["integrations"])
def floppy_status() -> dict[str, object]:
    client = get_floppy_client()
    if client is None:
        return {
            "configured": False,
            "reachable": False,
            "authenticated": False,
            "boardgame_api": False,
            "schema": {
                "available": False,
                "media_write": False,
                "collection_write": False,
                "write_contract_ready": False,
            },
        }

    status: dict[str, object] = {
        "configured": True,
        "base_url": client.config.normalized_url,
        "reachable": False,
        "authenticated": False,
        "boardgame_api": False,
    }

    try:
        info = client.info()
        status["reachable"] = True
        status["info"] = {
            key: info[key]
            for key in ("name", "version", "app", "commit")
            if key in info
        }
    except FloppyError as exc:
        status["error"] = {"kind": exc.kind, "message": str(exc)}
        status["schema"] = {
            "available": False,
            "media_write": False,
            "collection_write": False,
            "write_contract_ready": False,
        }
        return status

    try:
        client.boardgames_page(limit=1, offset=0)
        status["authenticated"] = True
        status["boardgame_api"] = True
    except FloppyError as exc:
        status["error"] = {"kind": exc.kind, "message": str(exc)}
        status["schema"] = {
            "available": False,
            "media_write": False,
            "collection_write": False,
            "write_contract_ready": False,
        }
        return status

    status["schema"] = client.schema_capabilities()
    return status


@app.get("/api/integrations/floppy/preview", tags=["integrations"])
def floppy_preview() -> dict[str, object]:
    client = get_floppy_client()
    if client is None:
        raise HTTPException(
            status_code=409,
            detail="Floppy is not configured. Open Impostazioni and configure URL and API token.",
        )

    database = get_database()
    database.initialize()

    try:
        remote_games = client.boardgames()
        collection_entries = client.collection_entries()
        capabilities = client.schema_capabilities()
    except FloppyError as exc:
        raise floppy_http_error(exc) from exc

    preview = build_sync_preview(
        local_owned_games(database),
        remote_games,
        collection_entries,
        load_floppy_links(database),
    )
    preview["mode"] = "dry_run"
    preview["apply_supported"] = bool(capabilities.get("write_contract_ready"))
    preview["schema"] = capabilities
    preview["note"] = (
        "Sync is add-only: it never removes Floppy media, collection entries, "
        "history, or local BoardGameCompanion records."
    )
    return preview


@app.post("/api/integrations/floppy/reconcile-links", tags=["integrations"])
def floppy_reconcile_links() -> dict[str, object]:
    client = get_floppy_client()
    if client is None:
        raise HTTPException(
            status_code=409,
            detail="Floppy is not configured. Open Impostazioni and configure URL and API token.",
        )

    database = get_database()
    database.initialize()

    try:
        collection_entries = client.collection_entries()
    except FloppyError as exc:
        raise floppy_http_error(exc) from exc

    return reconcile_floppy_links(database, collection_entries)


@app.post("/api/integrations/floppy/sync", tags=["integrations"])
def floppy_sync(payload: FloppySyncRequest) -> dict[str, object]:
    client = get_floppy_client()
    if client is None:
        raise HTTPException(
            status_code=409,
            detail="Floppy is not configured. Open Impostazioni and configure URL and API token.",
        )

    capabilities = client.schema_capabilities()
    if not capabilities.get("write_contract_ready"):
        raise HTTPException(
            status_code=409,
            detail=(
                "The configured Floppy instance does not expose the validated "
                "media + collection write contract."
            ),
        )

    database = get_database()
    database.initialize()

    try:
        return apply_floppy_sync(
            database,
            client,
            expected_plan_hash=payload.plan_hash,
            batch_size=payload.batch_size,
        )
    except FloppyPlanChanged as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FloppyError as exc:
        raise floppy_http_error(exc) from exc
