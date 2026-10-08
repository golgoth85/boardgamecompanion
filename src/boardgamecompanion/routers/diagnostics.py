from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter

from boardgamecompanion.app_settings import (
    resolve_bgg_settings,
    resolve_crowdfunding_settings,
    resolve_rag_settings,
    resolve_youtube_settings,
)
from boardgamecompanion.dependencies import get_database
from boardgamecompanion.settings import settings

router = APIRouter(tags=["diagnostics"])


def _status_counts(connection, table: str) -> dict[str, int]:
    rows = connection.execute(
        f"SELECT status,COUNT(*) AS count FROM {table} GROUP BY status"
    ).fetchall()
    return {str(row["status"]): int(row["count"]) for row in rows}


def _cache_info(path: Path) -> dict[str, object]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"exists": False, "updated_at": None, "bytes": 0}
    return {
        "exists": True,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        "bytes": int(stat.st_size),
    }


@router.get("/api/diagnostics")
def diagnostics() -> dict[str, object]:
    database = get_database()
    database.initialize()
    bgg = resolve_bgg_settings(database)
    rag = resolve_rag_settings(database)
    youtube = resolve_youtube_settings(database)
    crowdfunding = resolve_crowdfunding_settings(database)

    with database.connect() as connection:
        sync = connection.execute(
            "SELECT * FROM bgg_collection_sync_state WHERE id=1"
        ).fetchone()
        notifications = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN read_at IS NULL THEN 1 ELSE 0 END) AS unread
            FROM notifications
            """
        ).fetchone()
        expansion_scan = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN baseline_complete=1 THEN 1 ELSE 0 END) AS baselined,
                   SUM(CASE WHEN last_error IS NOT NULL THEN 1 ELSE 0 END) AS errors
            FROM expansion_scan_state
            """
        ).fetchone()
        wishlist_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM personal_wishlist"
            ).fetchone()["count"]
            or 0
        )
        list_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM saved_game_lists"
            ).fetchone()["count"]
            or 0
        )
        rulebook_discovery = _status_counts(connection, "rulebook_discovery_games")
        document_indexing = _status_counts(connection, "document_index_jobs")

    return {
        "schema_version": database.schema_version(),
        "bgg": {
            "configured": bool(bgg.configured),
            "collection_sync_configured": bool(bgg.collection_sync_configured),
            "last_success_at": sync["last_success_at"] if sync else None,
            "last_error": sync["last_error"] if sync else None,
        },
        "assistant": {
            "generation_order": list(rag.generation_provider_order),
            "embedding_order": list(rag.embedding_provider_order),
            "youtube_configured": bool(youtube.api_key),
        },
        "crowdfunding": {
            "kickstarter_configured": bool(crowdfunding.apify_token),
            "cache": _cache_info(settings.crowdfunding_cache_path),
        },
        "suggestions": {
            "cache": _cache_info(settings.suggestions_cache_path),
            "editorial_cache": _cache_info(settings.suggestions_editorial_cache_path),
        },
        "rulebooks": {
            "discovery": rulebook_discovery,
            "indexing": document_indexing,
        },
        "personal": {
            "wishlist_count": wishlist_count,
            "list_count": list_count,
            "notifications_total": int(notifications["total"] or 0),
            "notifications_unread": int(notifications["unread"] or 0),
            "expansion_scans": int(expansion_scan["total"] or 0),
            "expansion_baselines": int(expansion_scan["baselined"] or 0),
            "expansion_scan_errors": int(expansion_scan["errors"] or 0),
        },
    }
