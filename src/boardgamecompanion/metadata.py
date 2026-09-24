from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from boardgamecompanion.database import Database

PROVIDER = "floppy_bgg"
SOURCE = "bgg"
MAX_PROVIDER_PAYLOAD_BYTES = 512 * 1024


class GameMetadataError(ValueError):
    pass


class GameMetadataGameNotFound(GameMetadataError):
    pass


class GameMetadataInvalidProviderPayload(GameMetadataError):
    pass


def _clean_text(value: Any, *, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    return value[:max_length]


def _safe_http_url(value: Any) -> str | None:
    value = _clean_text(value, max_length=4000)
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def _normalize_genres(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in value[:100]:
        item = _clean_text(raw, max_length=200)
        if item is None:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _payload_digest(payload: dict[str, Any]) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GameMetadataInvalidProviderPayload(
            "Floppy BGG metadata is not valid JSON data"
        ) from exc
    if len(encoded) > MAX_PROVIDER_PAYLOAD_BYTES:
        raise GameMetadataInvalidProviderPayload(
            "Floppy BGG metadata exceeds the cache payload limit"
        )
    return hashlib.sha256(encoded).hexdigest()


def normalize_floppy_bgg_payload(
    bgg_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GameMetadataInvalidProviderPayload(
            "Floppy BGG metadata must be an object"
        )

    source = _clean_text(payload.get("source"), max_length=64)
    media_id = _clean_text(payload.get("media_id"), max_length=128)
    if source != SOURCE or media_id != str(int(bgg_id)):
        raise GameMetadataInvalidProviderPayload(
            "Floppy BGG metadata identity does not match the requested game"
        )

    media_type = _clean_text(payload.get("media_type"), max_length=64)
    if media_type is not None and media_type != "boardgame":
        raise GameMetadataInvalidProviderPayload(
            "Floppy returned metadata for a non-boardgame item"
        )

    details = payload.get("details")
    if not isinstance(details, dict):
        details = {}

    return {
        "provider": PROVIDER,
        "source": SOURCE,
        "media_id": media_id,
        "provider_title": _clean_text(payload.get("title"), max_length=500),
        "source_url": _safe_http_url(payload.get("source_url")),
        "image_url": _safe_http_url(payload.get("image")),
        "synopsis": _clean_text(payload.get("synopsis"), max_length=100_000),
        "genres": _normalize_genres(payload.get("genres")),
        "score": _to_float(payload.get("score")),
        "score_count": _to_int(payload.get("score_count")),
        "year_published": _to_int(details.get("year")),
        "players_text": _clean_text(details.get("players"), max_length=500),
        "playtime_text": _clean_text(details.get("playtime"), max_length=500),
        "min_age": _clean_text(details.get("min_age"), max_length=500),
        "designers": _clean_text(details.get("designers"), max_length=2000),
        "publishers": _clean_text(details.get("publishers"), max_length=2000),
        "payload_sha256": _payload_digest(payload),
    }


def _row_to_metadata(row: Any) -> dict[str, Any]:
    try:
        genres = json.loads(row["genres_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        genres = []
    if not isinstance(genres, list):
        genres = []

    return {
        "provider": row["provider"],
        "source": row["source"],
        "media_id": row["media_id"],
        "title": row["provider_title"],
        "source_url": row["source_url"],
        "image_url": row["image_url"],
        "synopsis": row["synopsis"],
        "genres": [item for item in genres if isinstance(item, str)],
        "score": row["score"],
        "score_count": row["score_count"],
        "year_published": row["year_published"],
        "players": row["players_text"],
        "playtime": row["playtime_text"],
        "min_age": row["min_age"],
        "designers": row["designers"],
        "publishers": row["publishers"],
        "payload_sha256": row["payload_sha256"],
        "fetched_at": row["fetched_at"],
        "updated_at": row["updated_at"],
    }


class GameMetadataStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_for_game(self, bgg_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT m.*
                FROM game_metadata_cache m
                JOIN board_games g ON g.id = m.board_game_id
                WHERE g.bgg_id = ? AND m.provider = ?
                """,
                (int(bgg_id), PROVIDER),
            ).fetchone()
        return _row_to_metadata(row) if row is not None else None

    def upsert_from_floppy(
        self,
        bgg_id: int,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]:
        normalized = normalize_floppy_bgg_payload(bgg_id, payload)
        timestamp = (now or datetime.now(UTC)).isoformat()
        genres_json = json.dumps(
            normalized["genres"],
            ensure_ascii=False,
            separators=(",", ":"),
        )

        values = {
            "source": normalized["source"],
            "media_id": normalized["media_id"],
            "provider_title": normalized["provider_title"],
            "source_url": normalized["source_url"],
            "image_url": normalized["image_url"],
            "synopsis": normalized["synopsis"],
            "genres_json": genres_json,
            "score": normalized["score"],
            "score_count": normalized["score_count"],
            "year_published": normalized["year_published"],
            "players_text": normalized["players_text"],
            "playtime_text": normalized["playtime_text"],
            "min_age": normalized["min_age"],
            "designers": normalized["designers"],
            "publishers": normalized["publishers"],
            "payload_sha256": normalized["payload_sha256"],
        }

        with self.database.transaction(immediate=True) as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id = ?",
                (int(bgg_id),),
            ).fetchone()
            if game is None:
                raise GameMetadataGameNotFound(
                    f"Board game BGG #{int(bgg_id)} not found"
                )

            existing = connection.execute(
                """
                SELECT *
                FROM game_metadata_cache
                WHERE board_game_id = ? AND provider = ?
                """,
                (game["id"], PROVIDER),
            ).fetchone()
            changed = existing is None or any(
                existing[key] != value for key, value in values.items()
            )
            updated_at = (
                timestamp
                if changed or existing is None
                else existing["updated_at"]
            )

            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            assignments = ", ".join(
                f"{column} = excluded.{column}" for column in values
            )
            connection.execute(
                f"""
                INSERT INTO game_metadata_cache (
                    board_game_id, provider, {columns}, fetched_at, updated_at
                ) VALUES (?, ?, {placeholders}, ?, ?)
                ON CONFLICT(board_game_id, provider) DO UPDATE SET
                    {assignments},
                    fetched_at = excluded.fetched_at,
                    updated_at = excluded.updated_at
                """,
                (
                    game["id"],
                    PROVIDER,
                    *values.values(),
                    timestamp,
                    updated_at,
                ),
            )
            stored = connection.execute(
                """
                SELECT *
                FROM game_metadata_cache
                WHERE board_game_id = ? AND provider = ?
                """,
                (game["id"], PROVIDER),
            ).fetchone()

        assert stored is not None
        return _row_to_metadata(stored), changed


METADATA_CATALOG_SELECT = """
    m.provider AS metadata_provider,
    m.source AS metadata_source,
    m.media_id AS metadata_media_id,
    m.provider_title AS metadata_title,
    m.source_url AS metadata_source_url,
    m.image_url AS metadata_image_url,
    m.synopsis AS metadata_synopsis,
    m.genres_json AS metadata_genres_json,
    m.score AS metadata_score,
    m.score_count AS metadata_score_count,
    m.year_published AS metadata_year_published,
    m.players_text AS metadata_players,
    m.playtime_text AS metadata_playtime,
    m.min_age AS metadata_min_age,
    m.designers AS metadata_designers,
    m.publishers AS metadata_publishers,
    m.payload_sha256 AS metadata_payload_sha256,
    m.fetched_at AS metadata_fetched_at,
    m.updated_at AS metadata_updated_at
"""


def metadata_from_catalog_row(row: Any) -> dict[str, Any] | None:
    if row["metadata_provider"] is None:
        return None
    try:
        genres = json.loads(row["metadata_genres_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        genres = []
    if not isinstance(genres, list):
        genres = []

    return {
        "provider": row["metadata_provider"],
        "source": row["metadata_source"],
        "media_id": row["metadata_media_id"],
        "title": row["metadata_title"],
        "source_url": row["metadata_source_url"],
        "image_url": row["metadata_image_url"],
        "synopsis": row["metadata_synopsis"],
        "genres": [item for item in genres if isinstance(item, str)],
        "score": row["metadata_score"],
        "score_count": row["metadata_score_count"],
        "year_published": row["metadata_year_published"],
        "players": row["metadata_players"],
        "playtime": row["metadata_playtime"],
        "min_age": row["metadata_min_age"],
        "designers": row["metadata_designers"],
        "publishers": row["metadata_publishers"],
        "payload_sha256": row["metadata_payload_sha256"],
        "fetched_at": row["metadata_fetched_at"],
        "updated_at": row["metadata_updated_at"],
    }
