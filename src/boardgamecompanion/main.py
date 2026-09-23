from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from fastapi.staticfiles import StaticFiles

from boardgamecompanion import __version__
from boardgamecompanion.app_settings import (
    resolve_floppy_settings,
    save_floppy_settings,
)
from boardgamecompanion.bgg_csv import BggCsvError, BggCsvImporter
from boardgamecompanion.catalog import Catalog, SORT_SQL
from boardgamecompanion.database import Database
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
from boardgamecompanion.settings import settings

WEB_DIR = Path(__file__).parent / "web"


def get_database() -> Database:
    return Database(settings.database_path)


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    get_database().initialize()
    yield


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
