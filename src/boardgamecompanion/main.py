from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from boardgamecompanion import __version__
from boardgamecompanion.bgg_csv import BggCsvError, BggCsvImporter
from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database
from boardgamecompanion.settings import settings


def get_database() -> Database:
    return Database(settings.database_path)


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
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    return Catalog(database).list_games(
        query=q,
        item_type=item_type,
        owned=owned,
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
