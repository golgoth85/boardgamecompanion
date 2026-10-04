import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from boardgamecompanion import __version__
from boardgamecompanion.answer_generation import (
    AnswerGenerationService,
    AnswerProtocolError,
    AnswerProviderError,
    AnswerSourceNotReady,
    GeminiGenerationProvider,
    LMStudioGenerationProvider,
    OllamaGenerationProvider,
)
from boardgamecompanion.app_settings import (
    activate_embedding_provider,
    resolve_bgg_settings,
    resolve_rag_settings,
    save_bgg_settings,
    save_rag_settings,
)
from boardgamecompanion.bgg_collection_sync import (
    BggCollectionClient,
    BggCollectionConfig,
    BggCollectionSyncError,
    BggCollectionSyncService,
)
from boardgamecompanion.bgg_csv import BggCsvError, BggCsvImporter
from boardgamecompanion.bgg_metadata import (
    BggApiClient,
    BggApiConfig,
    BggMetadataError,
    BggMetadataStore,
)
from boardgamecompanion.catalog import SORT_SQL, Catalog
from boardgamecompanion.catalog_assistant import (
    CatalogAssistantError,
    CatalogAssistantService,
)
from boardgamecompanion.chunk_index import (
    ChunkIndexConflict,
    ChunkIndexCorruptSource,
    ChunkIndexDocumentNotFound,
    ChunkIndexError,
    ChunkIndexService,
    ChunkIndexSourceNotReady,
)
from boardgamecompanion.copies import (
    BoardGameNotFound,
    PhysicalCopyError,
    PhysicalCopyNotFound,
    PhysicalCopyStore,
)
from boardgamecompanion.database import Database
from boardgamecompanion.description_translation import (
    DescriptionTranslationError,
    DescriptionTranslationService,
)
from boardgamecompanion.gameplay_summary import (
    GameplaySummaryError,
    GameplaySummaryService,
)
from boardgamecompanion.documents import (
    BoardGameDocumentNotFound,
    DocumentError,
    DocumentNotFound,
    DocumentStore,
    DocumentTooLarge,
    InvalidPdf,
)
from boardgamecompanion.document_indexing import (
    DocumentIndexingBusy,
    DocumentIndexingError,
    DocumentIndexingService,
    enqueue_document_index,
    requeue_document_indexes_for_provider_change,
)
from boardgamecompanion.pdf_ingest import (
    PdfIngestDocumentNotFound,
    PdfIngestError,
    PdfIngestIntegrityError,
    PdfIngestParseError,
    PdfIngestService,
)
from boardgamecompanion.rate_limits import PersistentRateLimiter
from boardgamecompanion.embedding_retrieval import (
    EmbeddingConflict,
    EmbeddingCorruptRecord,
    EmbeddingDocumentNotFound,
    EmbeddingGameNotFound,
    EmbeddingProviderError,
    EmbeddingRetrievalService,
    EmbeddingSourceNotReady,
    GeminiEmbeddingProvider,
    LMStudioEmbeddingProvider,
    OllamaEmbeddingProvider,
)
from boardgamecompanion.rulebook_review import (
    RulebookReviewConflict,
    RulebookReviewCorruptRecord,
    RulebookReviewError,
    RulebookReviewNotFound,
    RulebookReviewQueue,
)
from boardgamecompanion.rulebook_discovery import (
    RulebookDiscoveryBusy,
    RulebookDiscoveryError,
    RulebookDiscoveryNotFound,
    RulebookDiscoveryService,
)
from boardgamecompanion.rulebook_providers import production_rulebook_providers
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


def get_bgg_collection_sync_service() -> BggCollectionSyncService | None:
    database = get_database()
    database.initialize()
    resolved = resolve_bgg_settings(database)
    if not resolved.collection_sync_configured:
        return None
    client = BggCollectionClient(
        BggCollectionConfig(
            application_token=resolved.application_token or "",
            username=resolved.username or "",
            timeout_seconds=resolved.timeout_seconds,
            min_interval_seconds=resolved.min_interval_seconds,
        ),
        rate_limiter=PersistentRateLimiter(database).acquire,
    )
    return BggCollectionSyncService(
        database,
        client,
        interval_seconds=resolved.collection_sync_interval_seconds,
    )


def get_bgg_metadata_store() -> BggMetadataStore:
    database = get_database()
    database.initialize()
    resolved = resolve_bgg_settings(database)
    token = (resolved.application_token or "").strip()
    client = (
        BggApiClient(
            BggApiConfig(
                application_token=token,
                timeout_seconds=resolved.timeout_seconds,
                min_interval_seconds=resolved.min_interval_seconds,
            ),
            rate_limiter=PersistentRateLimiter(database).acquire,
        )
        if token
        else None
    )
    return BggMetadataStore(
        database,
        client,
        refresh_seconds=settings.bgg_metadata_refresh_seconds,
    )


def get_description_translation_service() -> DescriptionTranslationService:
    database = get_database()
    database.initialize()
    return DescriptionTranslationService(database)


def get_rulebook_discovery_service() -> RulebookDiscoveryService:
    database = get_database()
    database.initialize()
    return RulebookDiscoveryService(
        database,
        production_rulebook_providers(
            timeout_seconds=settings.rulebook_discovery_timeout_seconds,
            max_attempts=settings.rulebook_discovery_max_attempts,
            min_interval_seconds=settings.rulebook_discovery_min_interval_seconds,
            rate_limiter=PersistentRateLimiter(database).acquire,
        ),
        metadata_store=get_bgg_metadata_store(),
        refresh_seconds=settings.rulebook_discovery_refresh_seconds,
        empty_refresh_seconds=settings.rulebook_discovery_empty_refresh_seconds,
        retry_base_seconds=settings.rulebook_discovery_retry_base_seconds,
        retry_max_seconds=settings.rulebook_discovery_retry_max_seconds,
        lease_seconds=settings.rulebook_discovery_lease_seconds,
    )


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


class GameCompletionPayload(BaseModel):
    completed: bool
    completed_at: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )


class CatalogAssistantPayload(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class GameplaySummaryBatchPayload(BaseModel):
    bgg_ids: list[int] = Field(min_length=1, max_length=8)


class BggSettingsUpdate(BaseModel):
    application_token: str | None = Field(default=None, max_length=4096)
    clear_application_token: bool = False
    username: str | None = Field(default=None, max_length=128)


class RagSettingsUpdate(BaseModel):
    embedding_provider_order: list[Literal["ollama", "lmstudio", "gemini"]] = Field(
        min_length=1, max_length=3
    )
    generation_provider_order: list[Literal["ollama", "lmstudio", "gemini"]] = Field(
        min_length=1, max_length=3
    )
    ollama_url: str | None = Field(default=None, max_length=4096)
    ollama_embedding_model: str | None = Field(default=None, max_length=500)
    ollama_generation_model: str | None = Field(default=None, max_length=500)
    lmstudio_url: str | None = Field(default=None, max_length=4096)
    lmstudio_api_key: str | None = Field(default=None, max_length=4096)
    clear_lmstudio_api_key: bool = False
    lmstudio_embedding_model: str | None = Field(default=None, max_length=500)
    lmstudio_generation_model: str | None = Field(default=None, max_length=500)
    lmstudio_generation_timeout_seconds: float = Field(default=300.0, ge=1.0, le=900.0)
    lmstudio_generation_max_tokens: int = Field(default=512, ge=64, le=4096)
    lmstudio_generation_disable_thinking: bool = True
    gemini_url: str | None = Field(default=None, max_length=4096)
    gemini_api_key: str | None = Field(default=None, max_length=4096)
    clear_gemini_api_key: bool = False
    gemini_embedding_model: str | None = Field(default=None, max_length=500)
    gemini_generation_model: str | None = Field(default=None, max_length=500)


class RetrievalPayload(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    language: str | None = Field(default=None, max_length=32)
    document_type: str | None = Field(default=None, max_length=64)
    version_label: str | None = Field(default=None, max_length=500)
    edition: str | None = Field(default=None, max_length=500)
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=-1.0, ge=-1.0, le=1.0)


class AnswerPayload(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    language: str | None = Field(default=None, max_length=32)
    document_type: str | None = Field(default=None, max_length=64)
    version_label: str | None = Field(default=None, max_length=500)
    edition: str | None = Field(default=None, max_length=500)
    top_k: int = Field(default=8, ge=1, le=20)
    min_score: float = Field(default=-1.0, ge=-1.0, le=1.0)


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


async def _rulebook_discovery_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.rulebook_discovery_poll_seconds)
            break
        except TimeoutError:
            pass
        try:
            await asyncio.to_thread(
                get_rulebook_discovery_service().run_due,
                limit=settings.rulebook_discovery_batch_size,
            )
            await asyncio.to_thread(
                get_rulebook_update_service().synchronize_approved_targets
            )
        except Exception:
            LOGGER.exception("Scheduled rulebook discovery worker failed")


def _run_bgg_collection_sync(force: bool = False) -> dict[str, object] | None:
    service = get_bgg_collection_sync_service()
    if service is None:
        return None
    result = service.sync(force=force)
    if result is None:
        return None

    try:
        get_rulebook_discovery_service().synchronize_catalog()
    except Exception:
        LOGGER.exception("BGG collection sync: rulebook catalog synchronization failed")

    new_ids = list(result.created_bgg_ids)
    if new_ids:
        store = get_bgg_metadata_store()
        for offset in range(0, len(new_ids), 20):
            chunk = new_ids[offset:offset + 20]
            try:
                store.refresh_many(chunk, force=True)
            except Exception:
                LOGGER.exception(
                    "BGG collection sync: metadata enrichment failed for %s",
                    chunk,
                )
        for bgg_id in new_ids[:10]:
            try:
                get_description_translation_service().translate(bgg_id)
            except Exception:
                LOGGER.exception(
                    "BGG collection sync: Italian description translation failed for BGG #%s",
                    bgg_id,
                )

    return result.to_dict()


async def _bgg_collection_sync_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(_run_bgg_collection_sync, False)
        except Exception:
            LOGGER.exception("Scheduled BGG collection sync failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.bgg_collection_sync_poll_seconds,
            )
            break
        except TimeoutError:
            pass


async def _bgg_metadata_backfill_once(stop_event: asyncio.Event) -> None:
    database = get_database()
    database.initialize()
    if not resolve_bgg_settings(database).configured:
        return

    catalog = Catalog(database)
    store = get_bgg_metadata_store()
    for _ in range(10):
        if stop_event.is_set():
            return
        identifiers = await asyncio.to_thread(catalog.refreshable_metadata_ids, limit=20)
        if not identifiers:
            return
        try:
            await asyncio.to_thread(store.refresh_many, identifiers, force=True)
        except Exception:
            LOGGER.exception("Initial BGG metadata backfill failed")
            return


async def _document_index_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.document_index_poll_seconds)
            break
        except TimeoutError:
            pass
        try:
            await asyncio.to_thread(
                get_document_indexing_service().run_due,
                limit=settings.document_index_batch_size,
            )
        except Exception:
            LOGGER.exception("Scheduled document indexing worker failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    get_database().initialize()

    worker_tasks: list[asyncio.Task[None]] = []
    worker_stop = asyncio.Event()
    worker_tasks.append(asyncio.create_task(_bgg_collection_sync_worker(worker_stop)))
    worker_tasks.append(asyncio.create_task(_bgg_metadata_backfill_once(worker_stop)))
    if settings.rulebook_update_worker_enabled:
        try:
            await asyncio.to_thread(
                get_rulebook_update_service().synchronize_approved_targets
            )
        except Exception:
            LOGGER.exception(
                "Initial rulebook update target synchronization failed"
            )
        worker_tasks.append(asyncio.create_task(_rulebook_update_worker(worker_stop)))
    if settings.rulebook_discovery_worker_enabled:
        try:
            await asyncio.to_thread(get_rulebook_discovery_service().synchronize_catalog)
        except Exception:
            LOGGER.exception("Initial rulebook discovery synchronization failed")
        worker_tasks.append(asyncio.create_task(_rulebook_discovery_worker(worker_stop)))
    if settings.document_index_worker_enabled:
        try:
            await asyncio.to_thread(get_document_indexing_service().synchronize_documents)
        except Exception:
            LOGGER.exception("Initial document index synchronization failed")
        worker_tasks.append(asyncio.create_task(_document_index_worker(worker_stop)))

    try:
        yield
    finally:
        if worker_tasks:
            worker_stop.set()
            await asyncio.gather(*worker_tasks)


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


@app.get("/discovery", include_in_schema=False)
def web_discovery() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/rankings", include_in_schema=False)
def web_rankings() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/play-next", include_in_schema=False)
def web_play_next() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/new", include_in_schema=False)
def web_new() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/completed", include_in_schema=False)
def web_completed() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/explore", include_in_schema=False)
def web_explore() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/categories", include_in_schema=False)
def web_categories() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/mechanics", include_in_schema=False)
def web_mechanics() -> FileResponse:
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

    get_rulebook_discovery_service().synchronize_catalog()

    return {**result.to_dict(), "snapshot": str(snapshot_path)}


@app.get("/api/games", tags=["catalog"])
def list_games(
    q: str | None = Query(default=None, min_length=1),
    item_type: str | None = Query(default=None),
    owned: bool | None = Query(default=None),
    supports_players: int | None = Query(default=None, ge=1, le=30),
    ideal_players: int | None = Query(default=None, ge=1, le=30),
    player_age: int | None = Query(default=None, ge=3, le=99),
    weight: Literal["light", "medium", "heavy"] | None = Query(default=None),
    max_minutes: int | None = Query(default=None, ge=1, le=1440),
    min_rating: float | None = Query(default=None, ge=0, le=10),
    category: str | None = Query(default=None, min_length=1, max_length=500),
    mechanic: str | None = Query(default=None, min_length=1, max_length=500),
    completed: bool | None = Query(default=None),
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
        supports_players=supports_players,
        ideal_players=ideal_players,
        player_age=player_age,
        weight=weight,
        max_minutes=max_minutes,
        min_rating=min_rating,
        category=category,
        mechanic=mechanic,
        completed=completed,
        sort=sort if sort in SORT_SQL else "title",
        limit=limit,
        offset=offset,
    )


@app.get("/api/catalog/rankings", tags=["catalog"])
def catalog_rankings(
    mode: Literal[
        "overall",
        "outside_top",
        "quality_time",
        "gateway",
        "expert",
        "safe_choice",
        "personal_favorites",
    ] = Query(default="overall"),
    category: str | None = Query(default=None, min_length=1, max_length=500),
    mechanic: str | None = Query(default=None, min_length=1, max_length=500),
    ideal_players: int | None = Query(default=None, ge=1, le=30),
    max_minutes: int | None = Query(default=None, ge=1, le=1440),
    weight: Literal["light", "medium", "heavy"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    payload = Catalog(database).rankings(
        mode=mode,
        category=category,
        mechanic=mechanic,
        ideal_players=ideal_players,
        max_minutes=max_minutes,
        weight=weight,
        limit=limit,
    )
    games = [
        item.get("game", {})
        for item in payload.get("items", [])
        if isinstance(item, dict)
    ]
    bgg_ids = [
        int(game["bgg_id"])
        for game in games
        if isinstance(game, dict) and game.get("bgg_id") is not None
    ]
    cached = GameplaySummaryService(database).get_cached_many(bgg_ids)
    for game in games:
        if not isinstance(game, dict) or game.get("bgg_id") is None:
            continue
        summary = cached.get(int(game["bgg_id"]))
        game["gameplay_summary"] = summary["summary"] if summary else None
    return payload


@app.post("/api/catalog/gameplay-summaries/ensure", tags=["catalog"])
def ensure_gameplay_summaries(
    payload: GameplaySummaryBatchPayload,
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        return GameplaySummaryService(database).ensure_many(payload.bgg_ids)
    except GameplaySummaryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/catalog/explore", tags=["catalog"])
def explore_catalog(
    category: list[str] | None = Query(default=None, max_length=500),
    mechanic: list[str] | None = Query(default=None, max_length=500),
    supports_players: int | None = Query(default=None, ge=1, le=30),
    ideal_players: int | None = Query(default=None, ge=1, le=30),
    player_age: int | None = Query(default=None, ge=3, le=99),
    weight: Literal["light", "medium", "heavy"] | None = Query(default=None),
    max_minutes: int | None = Query(default=None, ge=1, le=1440),
    min_rating: float | None = Query(default=None, ge=0, le=10),
    limit: int = Query(default=250, ge=1, le=250),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    return Catalog(database).explore(
        categories=category,
        mechanics=mechanic,
        supports_players=supports_players,
        ideal_players=ideal_players,
        player_age=player_age,
        weight=weight,
        max_minutes=max_minutes,
        min_rating=min_rating,
        limit=limit,
    )


@app.get("/api/catalog/facets", tags=["catalog"])
def get_catalog_facets(
    limit: int = Query(default=40, ge=1, le=100),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    return Catalog(database).facets(owned_only=True, limit=limit)


@app.post("/api/catalog/assistant", tags=["catalog"])
def ask_catalog_assistant(payload: CatalogAssistantPayload) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        return CatalogAssistantService(database).ask(payload.query)
    except CatalogAssistantError as exc:
        detail = str(exc)
        code = 503 if "configurato" in detail or "restituito" in detail else 400
        raise HTTPException(status_code=code, detail=detail) from exc


@app.get("/api/games/{bgg_id}", tags=["catalog"])
def get_game(bgg_id: int) -> dict[str, object]:
    database = get_database()
    database.initialize()
    game = Catalog(database).get_game(bgg_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Board game not found")
    game["bgg_metadata"] = get_bgg_metadata_store().get(bgg_id)
    cached_translation = DescriptionTranslationService(database).get_cached(bgg_id)
    game["description_it"] = (
        cached_translation["translated_text"] if cached_translation else None
    )
    return game


@app.put("/api/games/{bgg_id}/completion", tags=["catalog"])
def update_game_completion(
    bgg_id: int,
    payload: GameCompletionPayload,
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    now = datetime.now(UTC).isoformat()
    with database.transaction(immediate=True) as connection:
        row = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id=?",
            (bgg_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Board game not found")
        board_game_id = int(row["id"])
        if payload.completed:
            completed_at = payload.completed_at or datetime.now(UTC).date().isoformat()
            connection.execute(
                """
                INSERT INTO game_progress(
                    board_game_id,completed_at,created_at,updated_at
                ) VALUES(?,?,?,?)
                ON CONFLICT(board_game_id) DO UPDATE SET
                    completed_at=excluded.completed_at,
                    updated_at=excluded.updated_at
                """,
                (board_game_id, completed_at, now, now),
            )
        else:
            connection.execute(
                "DELETE FROM game_progress WHERE board_game_id=?",
                (board_game_id,),
            )

    game = Catalog(database).get_game(bgg_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Board game not found")
    return {
        "bgg_id": bgg_id,
        "progress": game["progress"],
    }


@app.get("/api/games/{bgg_id}/description-it", tags=["catalog"])
def get_game_description_it(bgg_id: int) -> dict[str, object]:
    try:
        return get_description_translation_service().status(bgg_id)
    except DescriptionTranslationError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/games/{bgg_id}/description-it/translate", tags=["catalog"])
def translate_game_description_it(bgg_id: int) -> dict[str, object]:
    try:
        return get_description_translation_service().translate(bgg_id)
    except DescriptionTranslationError as exc:
        detail = str(exc)
        if "not found" in detail:
            code = 404
        elif "No BGG description" in detail:
            code = 409
        else:
            code = 503
        raise HTTPException(status_code=code, detail=detail) from exc


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

    with database.transaction(immediate=True) as connection:
        enqueue_document_index(connection, str(document["id"]))

    return {
        "created": created,
        "document": document,
        "indexing": "queued",
    }


@app.get("/api/documents/{document_id}", tags=["documents"])
def get_document(document_id: str) -> dict[str, object]:
    database = get_database()
    database.initialize()
    document = DocumentStore(database, settings.manuals_dir).get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.get("/api/documents/{document_id}/file", tags=["documents"])
def get_document_file(document_id: str) -> StreamingResponse:
    database = get_database()
    database.initialize()
    store = DocumentStore(database, settings.manuals_dir)
    try:
        handle = store.open_verified_file(
            document_id,
            prefix=".serve-",
        )
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    size = handle.seek(0, 2)
    handle.seek(0)

    def stream_verified_pdf():
        try:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            handle.close()

    return StreamingResponse(
        stream_verified_pdf(),
        media_type="application/pdf",
        headers={"Content-Length": str(size)},
    )



def get_pdf_ingest_service() -> PdfIngestService:
    database = get_database()
    database.initialize()
    return PdfIngestService(
        database,
        settings.manuals_dir,
        timeout_seconds=settings.pdf_parse_timeout_seconds,
        max_pages=settings.pdf_parse_max_pages,
        max_chars_per_page=settings.pdf_parse_max_chars_per_page,
        max_total_chars=settings.pdf_parse_max_total_chars,
        memory_mb=settings.pdf_parse_memory_mb,
    )


@app.post("/api/documents/{document_id}/ingest", tags=["documents"])
def ingest_document_pdf(
    document_id: str,
    force: bool = Query(default=False),
) -> dict[str, object]:
    try:
        return get_pdf_ingest_service().ingest(document_id, force=force)
    except PdfIngestDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PdfIngestIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PdfIngestParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PdfIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/documents/{document_id}/ingest", tags=["documents"])
def get_document_ingest(document_id: str) -> dict[str, object]:
    try:
        return get_pdf_ingest_service().status(document_id)
    except PdfIngestDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PdfIngestIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/documents/{document_id}/pages", tags=["documents"])
def list_document_pages(
    document_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    try:
        return get_pdf_ingest_service().list_pages(
            document_id,
            limit=limit,
            offset=offset,
        )
    except PdfIngestDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PdfIngestIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/documents/{document_id}/pages/{page_number}", tags=["documents"])
def get_document_page(document_id: str, page_number: int) -> dict[str, object]:
    if page_number < 1:
        raise HTTPException(status_code=400, detail="Page number must be >= 1")
    try:
        page = get_pdf_ingest_service().get_page(document_id, page_number)
    except PdfIngestDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PdfIngestIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if page is None:
        raise HTTPException(status_code=404, detail="Document page not found")
    return page



def get_chunk_index_service() -> ChunkIndexService:
    database = get_database()
    database.initialize()
    return ChunkIndexService(
        database,
        settings.manuals_dir,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
        min_break_chars=settings.chunk_min_break_chars,
    )


@app.post("/api/documents/{document_id}/chunks/build", tags=["documents"])
def build_document_chunks(
    document_id: str,
    force: bool = Query(default=False),
) -> dict[str, object]:
    try:
        return get_chunk_index_service().build(document_id, force=force)
    except ChunkIndexDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ChunkIndexSourceNotReady, ChunkIndexConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChunkIndexCorruptSource as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ChunkIndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/documents/{document_id}/chunk-index", tags=["documents"])
def get_document_chunk_index(document_id: str) -> dict[str, object]:
    try:
        return get_chunk_index_service().status(document_id)
    except ChunkIndexDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChunkIndexCorruptSource as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/documents/{document_id}/chunks", tags=["documents"])
def list_document_chunks(
    document_id: str,
    page_number: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    try:
        return get_chunk_index_service().list_chunks(
            document_id,
            page_number=page_number,
            limit=limit,
            offset=offset,
        )
    except ChunkIndexDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChunkIndexSourceNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChunkIndexCorruptSource as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/chunks/{chunk_id}", tags=["documents"])
def get_document_chunk(chunk_id: str) -> dict[str, object]:
    try:
        chunk = get_chunk_index_service().get_chunk(chunk_id)
    except ChunkIndexSourceNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChunkIndexCorruptSource as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if chunk is None:
        raise HTTPException(status_code=404, detail="Document chunk not found")
    return chunk



def _embedding_provider_label(selected: str, rag) -> str:
    if selected == "gemini":
        return "Gemini"
    if selected == "ollama":
        model = str(rag.ollama_embedding_model or "")
        return "Qwen" if "qwen" in model.lower() else "Ollama"
    model = str(rag.lmstudio_embedding_model or "")
    return "Qwen" if "qwen" in model.lower() else "LM Studio"


def _embedding_retrieval_service_for(
    database: Database,
    rag,
    selected: str,
) -> EmbeddingRetrievalService:
    if selected == "lmstudio":
        if not rag.lmstudio_url or not rag.lmstudio_embedding_model:
            raise EmbeddingProviderError(
                "LM Studio embedding provider is not configured; set "
                "BGC_LMSTUDIO_URL and BGC_LMSTUDIO_EMBEDDING_MODEL"
            )
        provider = LMStudioEmbeddingProvider(
            base_url=rag.lmstudio_url,
            model=rag.lmstudio_embedding_model,
            requested_dimensions=settings.lmstudio_embedding_dimensions,
            timeout_seconds=settings.lmstudio_embedding_timeout_seconds,
            verify_tls=settings.lmstudio_verify_tls,
            api_key=rag.lmstudio_api_key,
        )
        batch_size = settings.lmstudio_embedding_batch_size
    elif selected == "gemini":
        if not rag.gemini_api_key:
            raise EmbeddingProviderError(
                "Gemini embedding provider is not configured; set BGC_GEMINI_API_KEY"
            )
        provider = GeminiEmbeddingProvider(
            base_url=rag.gemini_url,
            model=rag.gemini_embedding_model,
            api_key=rag.gemini_api_key,
            requested_dimensions=settings.gemini_embedding_dimensions,
            timeout_seconds=settings.gemini_embedding_timeout_seconds,
            verify_tls=settings.gemini_verify_tls,
        )
        batch_size = settings.gemini_embedding_batch_size
    elif selected == "ollama":
        if not rag.ollama_url or not rag.ollama_embedding_model:
            raise EmbeddingProviderError(
                "Ollama embedding provider is not configured; set BGC_OLLAMA_URL "
                "and BGC_OLLAMA_EMBEDDING_MODEL"
            )
        provider = OllamaEmbeddingProvider(
            base_url=rag.ollama_url,
            model=rag.ollama_embedding_model,
            requested_dimensions=settings.ollama_embedding_dimensions,
            timeout_seconds=settings.ollama_embedding_timeout_seconds,
            verify_tls=settings.ollama_verify_tls,
        )
        batch_size = settings.ollama_embedding_batch_size
    else:
        raise EmbeddingProviderError(
            f"Unsupported embedding provider: {selected}"
        )

    return EmbeddingRetrievalService(
        database,
        get_chunk_index_service(),
        provider,
        batch_size=batch_size,
        max_candidates=settings.retrieval_max_candidates,
    )


def get_embedding_retrieval_service() -> EmbeddingRetrievalService:
    database = get_database()
    database.initialize()
    rag = resolve_rag_settings(database)
    try:
        return _embedding_retrieval_service_for(
            database,
            rag,
            rag.embedding_provider,
        )
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _embedding_attempt_message(attempts: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for attempt in attempts:
        if attempt["status"] == "ok":
            parts.append(f"{attempt['label']} OK")
        else:
            detail = attempt.get("error", "").strip()
            parts.append(
                f"{attempt['label']} failed"
                + (f" ({detail})" if detail else "")
            )
    return " -> ".join(parts)


def build_document_embeddings_with_failover(
    document_id: str,
    *,
    force: bool = False,
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    rag = resolve_rag_settings(database)
    attempts: list[dict[str, str]] = []
    last_error: EmbeddingProviderError | None = None

    for index, selected in enumerate(rag.embedding_provider_order):
        label = _embedding_provider_label(selected, rag)
        try:
            service = _embedding_retrieval_service_for(database, rag, selected)
            result = service.build(document_id, force=force)
        except EmbeddingProviderError as exc:
            last_error = exc
            attempts.append(
                {
                    "provider": selected,
                    "label": label,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            continue

        attempts.append(
            {
                "provider": selected,
                "label": label,
                "status": "ok",
                "error": "",
            }
        )
        message = _embedding_attempt_message(attempts)
        requeued_documents = 0

        if index > 0:
            # A secondary embedding model uses a different vector space. Make
            # the successful fallback the sole active embedding provider and
            # requeue the remaining documents so retrieval never mixes vector
            # spaces from different models.
            activate_embedding_provider(database, selected)
            requeued_documents = requeue_document_indexes_for_provider_change(
                database,
                exclude_document_id=document_id,
            )
            LOGGER.warning(
                "Embedding provider failover activated: %s; requeued_documents=%s",
                message,
                requeued_documents,
            )

        return {
            **result,
            "provider_attempts": attempts,
            "provider_message": message,
            "active_provider": selected,
            "requeued_documents": requeued_documents,
        }

    message = _embedding_attempt_message(attempts)
    LOGGER.error("Embedding provider failover exhausted: %s", message)
    if last_error is None:
        raise EmbeddingProviderError("No embedding provider is configured")
    raise EmbeddingProviderError(message) from last_error


def get_document_indexing_service() -> DocumentIndexingService:
    database = get_database()
    database.initialize()
    return DocumentIndexingService(
        database,
        ingest=lambda document_id: get_pdf_ingest_service().ingest(document_id),
        chunks=lambda document_id: get_chunk_index_service().build(document_id),
        embeddings=lambda document_id: build_document_embeddings_with_failover(
            document_id
        ),
        retry_base_seconds=settings.document_index_retry_base_seconds,
        retry_max_seconds=settings.document_index_retry_max_seconds,
        lease_seconds=settings.document_index_lease_seconds,
    )


def embedding_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EmbeddingDocumentNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, EmbeddingGameNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (EmbeddingSourceNotReady, EmbeddingConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, EmbeddingProviderError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, EmbeddingCorruptRecord):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.post("/api/documents/{document_id}/embeddings/build", tags=["retrieval"])
def build_document_embeddings(
    document_id: str,
    force: bool = Query(default=False),
) -> dict[str, object]:
    try:
        return build_document_embeddings_with_failover(
            document_id,
            force=force,
        )
    except (
        EmbeddingDocumentNotFound,
        EmbeddingSourceNotReady,
        EmbeddingConflict,
        EmbeddingProviderError,
        EmbeddingCorruptRecord,
    ) as exc:
        raise embedding_http_error(exc) from exc


@app.get("/api/documents/{document_id}/embeddings", tags=["retrieval"])
def get_document_embeddings(document_id: str) -> dict[str, object]:
    try:
        return get_embedding_retrieval_service().status(document_id)
    except (
        EmbeddingDocumentNotFound,
        EmbeddingSourceNotReady,
        EmbeddingConflict,
        EmbeddingProviderError,
        EmbeddingCorruptRecord,
    ) as exc:
        raise embedding_http_error(exc) from exc


@app.post("/api/games/{bgg_id}/retrieve", tags=["retrieval"])
def retrieve_game_evidence(
    bgg_id: int,
    payload: RetrievalPayload,
) -> dict[str, object]:
    try:
        return get_embedding_retrieval_service().retrieve(
            bgg_id=bgg_id,
            query=payload.query,
            requested_language=payload.language,
            document_type=payload.document_type,
            version_label=payload.version_label,
            edition=payload.edition,
            top_k=payload.top_k,
            min_score=payload.min_score,
        )
    except (
        EmbeddingGameNotFound,
        EmbeddingConflict,
        EmbeddingProviderError,
        EmbeddingCorruptRecord,
    ) as exc:
        raise embedding_http_error(exc) from exc


def get_answer_generation_service() -> AnswerGenerationService:
    database = get_database()
    database.initialize()
    rag = resolve_rag_settings(database)
    selected = rag.generation_provider
    if selected == "lmstudio":
        if not rag.lmstudio_url or not rag.lmstudio_generation_model:
            raise HTTPException(
                status_code=503,
                detail=(
                    "LM Studio generation provider is not configured; set "
                    "BGC_LMSTUDIO_URL and BGC_LMSTUDIO_GENERATION_MODEL"
                ),
            )
        provider = LMStudioGenerationProvider(
            base_url=rag.lmstudio_url,
            model=rag.lmstudio_generation_model,
            timeout_seconds=rag.lmstudio_generation_timeout_seconds,
            verify_tls=settings.lmstudio_verify_tls,
            temperature=settings.lmstudio_generation_temperature,
            max_tokens=rag.lmstudio_generation_max_tokens,
            disable_thinking=rag.lmstudio_generation_disable_thinking,
            api_key=rag.lmstudio_api_key,
        )
    elif selected == "gemini":
        if not rag.gemini_api_key:
            raise HTTPException(
                status_code=503,
                detail="Gemini generation provider is not configured; set BGC_GEMINI_API_KEY",
            )
        provider = GeminiGenerationProvider(
            base_url=rag.gemini_url,
            model=rag.gemini_generation_model,
            api_key=rag.gemini_api_key,
            timeout_seconds=settings.gemini_generation_timeout_seconds,
            verify_tls=settings.gemini_verify_tls,
            temperature=settings.gemini_generation_temperature,
        )
    else:
        if not rag.ollama_url or not rag.ollama_generation_model:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Ollama generation provider is not configured; set BGC_OLLAMA_URL "
                    "and BGC_OLLAMA_GENERATION_MODEL"
                ),
            )
        provider = OllamaGenerationProvider(
            base_url=rag.ollama_url,
            model=rag.ollama_generation_model,
            timeout_seconds=settings.ollama_generation_timeout_seconds,
            verify_tls=settings.ollama_verify_tls,
            temperature=settings.ollama_generation_temperature,
        )
    return AnswerGenerationService(
        get_embedding_retrieval_service(),
        provider,
        max_evidence_chars=settings.answer_max_evidence_chars,
        max_claims=settings.answer_max_claims,
    )


@app.post("/api/games/{bgg_id}/answer", tags=["retrieval"])
def answer_game_question(
    bgg_id: int,
    payload: AnswerPayload,
) -> dict[str, object]:
    try:
        return get_answer_generation_service().answer(
            bgg_id=bgg_id,
            query=payload.query,
            requested_language=payload.language,
            document_type=payload.document_type,
            version_label=payload.version_label,
            edition=payload.edition,
            top_k=payload.top_k,
            min_score=payload.min_score,
        )
    except (
        EmbeddingGameNotFound,
        EmbeddingConflict,
        EmbeddingProviderError,
        EmbeddingCorruptRecord,
    ) as exc:
        raise embedding_http_error(exc) from exc
    except AnswerSourceNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AnswerProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AnswerProtocolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/rulebook-discovery", tags=["rulebooks"])
def list_rulebook_discovery(
    bgg_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=250, ge=1, le=500),
) -> dict[str, object]:
    payload = get_rulebook_discovery_service().list_status(bgg_id=bgg_id, limit=limit)
    payload["worker"] = {
        "enabled": settings.rulebook_discovery_worker_enabled,
        "poll_seconds": settings.rulebook_discovery_poll_seconds,
        "batch_size": settings.rulebook_discovery_batch_size,
    }
    return payload


@app.post("/api/rulebook-discovery/run", tags=["rulebooks"])
def run_rulebook_discovery_batch(
    limit: int = Query(default=5, ge=1, le=25),
) -> dict[str, object]:
    result = get_rulebook_discovery_service().run_due(limit=limit)
    get_rulebook_update_service().synchronize_approved_targets()
    return result


@app.post("/api/games/{bgg_id}/rulebook-discovery/run", tags=["rulebooks"])
def run_game_rulebook_discovery(bgg_id: int) -> dict[str, object]:
    service = get_rulebook_discovery_service()
    service.synchronize_catalog()
    try:
        result = service.run_game(bgg_id, force=True)
        get_rulebook_update_service().synchronize_approved_targets()
        return result
    except RulebookDiscoveryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RulebookDiscoveryBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RulebookDiscoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/games/{bgg_id}/rulebook-discovery", tags=["rulebooks"])
def get_game_rulebook_discovery(bgg_id: int) -> dict[str, object]:
    result = get_rulebook_discovery_service().list_status(bgg_id=bgg_id, limit=1)
    if not result["items"]:
        raise HTTPException(status_code=404, detail="Board game discovery state not found")
    return result["items"][0]


@app.get("/api/games/{bgg_id}/bgg-metadata", tags=["catalog"])
def get_game_bgg_metadata(bgg_id: int) -> dict[str, object]:
    database = get_database()
    database.initialize()
    item = get_bgg_metadata_store().get(bgg_id)
    return {"configured": resolve_bgg_settings(database).configured, "item": item}


@app.post("/api/games/{bgg_id}/bgg-metadata/refresh", tags=["catalog"])
def refresh_game_bgg_metadata(bgg_id: int) -> dict[str, object]:
    try:
        return get_bgg_metadata_store().refresh(bgg_id, force=True)
    except BggMetadataError as exc:
        code = 503 if "not configured" in str(exc) or "request" in str(exc) or "token" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@app.get("/api/document-index-jobs", tags=["documents"])
def list_document_index_jobs(
    document_id: str | None = Query(default=None),
    limit: int = Query(default=250, ge=1, le=500),
) -> dict[str, object]:
    service = get_document_indexing_service()
    service.synchronize_documents()
    return service.status(document_id=document_id, limit=limit)


@app.post("/api/documents/{document_id}/auto-index/run", tags=["documents"])
def run_document_auto_index(document_id: str) -> dict[str, object]:
    try:
        return get_document_indexing_service().run(document_id, force=True)
    except DocumentIndexingBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PdfIngestDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PdfIngestIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PdfIngestParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PdfIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChunkIndexDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ChunkIndexSourceNotReady, ChunkIndexConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChunkIndexCorruptSource as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ChunkIndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (
        EmbeddingDocumentNotFound,
        EmbeddingGameNotFound,
        EmbeddingSourceNotReady,
        EmbeddingConflict,
        EmbeddingProviderError,
        EmbeddingCorruptRecord,
    ) as exc:
        raise embedding_http_error(exc) from exc
    except DocumentIndexingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.post("/api/catalog/bgg-metadata/refresh-missing", tags=["catalog"])
def refresh_missing_bgg_metadata(
    limit: int = Query(default=20, ge=1, le=20),
) -> dict[str, object]:
    database = get_database()
    database.initialize()
    catalog = Catalog(database)
    identifiers = catalog.refreshable_metadata_ids(limit=limit)
    if not identifiers:
        return {"attempted": 0, "updated": 0, "remaining": 0, "items": []}
    try:
        refreshed = get_bgg_metadata_store().refresh_many(identifiers, force=True)
    except BggMetadataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    items = [
        {
            "bgg_id": identifier,
            "cover_url": refreshed[identifier].get("cover_url"),
            "description_available": bool(refreshed[identifier].get("description")),
        }
        for identifier in identifiers
        if identifier in refreshed
    ]
    return {
        "attempted": len(identifiers),
        "updated": len(items),
        "remaining": len(catalog.refreshable_metadata_ids(limit=20)),
        "items": items,
    }


@app.get("/api/catalog/stats", tags=["catalog"])
def catalog_stats() -> dict[str, int]:
    database = get_database()
    database.initialize()
    return Catalog(database).stats()


@app.get("/api/settings/rag", tags=["settings"])
def get_rag_settings() -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        return resolve_rag_settings(database).public_dict()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/settings/rag", tags=["settings"])
def update_rag_settings(payload: RagSettingsUpdate) -> dict[str, object]:
    database = get_database()
    database.initialize()
    try:
        resolved = save_rag_settings(
            database,
            embedding_provider_order=tuple(payload.embedding_provider_order),
            generation_provider_order=tuple(payload.generation_provider_order),
            ollama_url=payload.ollama_url,
            ollama_embedding_model=payload.ollama_embedding_model,
            ollama_generation_model=payload.ollama_generation_model,
            lmstudio_url=payload.lmstudio_url,
            lmstudio_api_key=payload.lmstudio_api_key,
            clear_lmstudio_api_key=payload.clear_lmstudio_api_key,
            lmstudio_embedding_model=payload.lmstudio_embedding_model,
            lmstudio_generation_model=payload.lmstudio_generation_model,
            lmstudio_generation_timeout_seconds=payload.lmstudio_generation_timeout_seconds,
            lmstudio_generation_max_tokens=payload.lmstudio_generation_max_tokens,
            lmstudio_generation_disable_thinking=payload.lmstudio_generation_disable_thinking,
            gemini_url=payload.gemini_url,
            gemini_api_key=payload.gemini_api_key,
            clear_gemini_api_key=payload.clear_gemini_api_key,
            gemini_embedding_model=payload.gemini_embedding_model,
            gemini_generation_model=payload.gemini_generation_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return resolved.public_dict()


@app.get("/api/settings/bgg", tags=["settings"])
def get_bgg_settings() -> dict[str, object]:
    database = get_database()
    database.initialize()
    return resolve_bgg_settings(database).public_dict()


@app.put("/api/settings/bgg", tags=["settings"])
def update_bgg_settings(payload: BggSettingsUpdate) -> dict[str, object]:
    database = get_database()
    database.initialize()
    resolved = save_bgg_settings(
        database,
        application_token=payload.application_token,
        clear_application_token=payload.clear_application_token,
        username=payload.username,
    )
    return resolved.public_dict()


@app.get("/api/bgg-collection-sync", tags=["imports"])
def get_bgg_collection_sync_status() -> dict[str, object]:
    database = get_database()
    database.initialize()
    resolved = resolve_bgg_settings(database)
    service = get_bgg_collection_sync_service()
    if service is None:
        return {
            "configured": False,
            "username": resolved.username,
            "due": False,
            "interval_seconds": resolved.collection_sync_interval_seconds,
            "last_attempt_at": None,
            "last_success_at": None,
            "last_error": None,
            "last_result": None,
        }
    return {
        "configured": True,
        "username": resolved.username,
        **service.status(),
    }


@app.post("/api/bgg-collection-sync/check", tags=["imports"])
def check_bgg_collection_sync(background_tasks: BackgroundTasks) -> dict[str, object]:
    service = get_bgg_collection_sync_service()
    if service is None:
        raise HTTPException(
            status_code=409,
            detail="Configure both BGG username and Application Token first",
        )
    status = service.status()
    scheduled = bool(status["due"])
    if scheduled:
        background_tasks.add_task(_run_bgg_collection_sync, False)
    return {**status, "configured": True, "scheduled": scheduled}


@app.post("/api/bgg-collection-sync/run", tags=["imports"])
def run_bgg_collection_sync() -> dict[str, object]:
    service = get_bgg_collection_sync_service()
    if service is None:
        raise HTTPException(
            status_code=409,
            detail="Configure both BGG username and Application Token first",
        )
    try:
        result = _run_bgg_collection_sync(True)
    except BggCollectionSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "configured": True,
        "result": result,
        **service.status(),
    }


@app.post("/api/settings/bgg/verify", tags=["settings"])
def verify_bgg_settings() -> dict[str, object]:
    database = get_database()
    database.initialize()
    resolved = resolve_bgg_settings(database)
    if not resolved.configured:
        raise HTTPException(status_code=409, detail="BGG application token is not configured")

    with database.connect() as connection:
        game = connection.execute(
            "SELECT bgg_id, title FROM board_games ORDER BY title COLLATE NOCASE, bgg_id LIMIT 1"
        ).fetchone()
    if game is None:
        return {
            "configured": True,
            "verified": False,
            "reason": "catalog_empty",
        }

    try:
        item = get_bgg_metadata_store().refresh(int(game["bgg_id"]), force=True)
    except BggMetadataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "configured": True,
        "verified": True,
        "bgg_id": int(game["bgg_id"]),
        "title": item.get("title") or game["title"],
    }

