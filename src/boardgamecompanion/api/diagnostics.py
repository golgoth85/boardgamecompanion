from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from boardgamecompanion.api.common import database
from boardgamecompanion.app_settings import (
    resolve_bgg_settings,
    resolve_crowdfunding_settings,
    resolve_rag_settings,
    resolve_youtube_settings,
)
from boardgamecompanion.settings import settings


router = APIRouter(prefix="/api/diagnostics", tags=["system"])


@router.get("")
def diagnostics():
    db = database()
    bgg = resolve_bgg_settings(db)
    crowdfunding = resolve_crowdfunding_settings(db)
    rag = resolve_rag_settings(db)
    youtube = resolve_youtube_settings(db)
    with db.connect() as connection:
        counts = {
            "games": connection.execute("SELECT COUNT(*) AS n FROM board_games").fetchone()["n"],
            "documents": connection.execute("SELECT COUNT(*) AS n FROM game_documents").fetchone()["n"],
            "notifications": connection.execute("SELECT COUNT(*) AS n FROM app_notifications").fetchone()["n"],
            "wishlist": connection.execute("SELECT COUNT(*) AS n FROM wishlist_items").fetchone()["n"],
            "lists": connection.execute("SELECT COUNT(*) AS n FROM game_lists").fetchone()["n"],
        }
    cache_files = {
        "suggestions": settings.suggestions_cache_path,
        "suggestions_editorial": settings.suggestions_editorial_cache_path,
        "crowdfunding": settings.crowdfunding_cache_path,
    }
    return {
        "schema_version": db.schema_version(),
        "database": str(settings.database_path),
        "services": {
            "bgg": {"configured": bgg.configured, "collection_sync": bgg.collection_sync_configured},
            "youtube": {"configured": youtube.configured},
            "crowdfunding": {"kickstarter_configured": crowdfunding.configured},
            "rag": {
                "embedding_order": list(rag.embedding_provider_order),
                "generation_order": list(rag.generation_provider_order),
                "lmstudio_wol_enabled": rag.lmstudio_wol_enabled,
            },
        },
        "counts": {key: int(value or 0) for key, value in counts.items()},
        "cache": {
            key: {
                "path": str(path),
                "exists": Path(path).exists(),
                "size_bytes": Path(path).stat().st_size if Path(path).exists() else 0,
            }
            for key, path in cache_files.items()
        },
    }
