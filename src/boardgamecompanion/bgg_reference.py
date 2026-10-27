from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from boardgamecompanion.app_settings import AppSettingsStore
from boardgamecompanion.database import Database
from boardgamecompanion.title_search import normalize_title_text

LOGGER = logging.getLogger(__name__)

DUMP_SOURCE_TYPE = "bgg_ranks_dump"
DUMP_DEFAULT_FILENAME = "boardgames_ranks.csv"
DUMP_REQUIRED_COLUMNS = {
    "id",
    "name",
    "yearpublished",
    "rank",
    "bayesaverage",
    "average",
    "usersrated",
    "is_expansion",
}

REFERENCE_TRANSLATION_KEY = "description_it"
MIN_VOTES_KEY = "bgg_reference_min_votes"
INCLUDE_EXPANSIONS_KEY = "bgg_reference_include_expansions"
MIN_WISHING_KEY = "bgg_reference_min_wishing"
DAILY_BUDGET_KEY = "bgg_reference_daily_budget"
CROWDFUNDING_GRACE_KEY = "bgg_reference_crowdfunding_grace_days"
DEFAULT_MIN_VOTES = 100
DEFAULT_MIN_WISHING = 50
MAX_MIN_WISHING = 10000
DEFAULT_DAILY_BUDGET = 1500
MAX_DAILY_BUDGET = 5000
DEFAULT_CROWDFUNDING_GRACE_DAYS = 540
MAX_CROWDFUNDING_GRACE_DAYS = 1095
MIN_VOTES_MINIMUM = 0
DUMP_WATCH_STATE_KEY = "dump_file_signature"


class BggReferenceError(ValueError):
    pass


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _to_int(value: str | None) -> int | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class ReferenceSettings:
    min_votes: int = DEFAULT_MIN_VOTES
    include_expansions: bool = True
    min_wishing: int = DEFAULT_MIN_WISHING
    daily_budget: int = DEFAULT_DAILY_BUDGET
    crowdfunding_grace_days: int = DEFAULT_CROWDFUNDING_GRACE_DAYS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bounded_int(raw: str | None, default: int, low: int, high: int | None) -> int:
    value = _to_int(raw)
    if value is None or value < low or (high is not None and value > high):
        return default
    return value


def load_reference_settings(database: Database) -> ReferenceSettings:
    values = AppSettingsStore(database).get_many(
        (MIN_VOTES_KEY, INCLUDE_EXPANSIONS_KEY, MIN_WISHING_KEY, DAILY_BUDGET_KEY, CROWDFUNDING_GRACE_KEY)
    )
    return ReferenceSettings(
        min_votes=_bounded_int(values[MIN_VOTES_KEY], DEFAULT_MIN_VOTES, MIN_VOTES_MINIMUM, None),
        include_expansions=values[INCLUDE_EXPANSIONS_KEY] != "0",
        min_wishing=_bounded_int(values[MIN_WISHING_KEY], DEFAULT_MIN_WISHING, 0, MAX_MIN_WISHING),
        daily_budget=_bounded_int(values[DAILY_BUDGET_KEY], DEFAULT_DAILY_BUDGET, 0, MAX_DAILY_BUDGET),
        crowdfunding_grace_days=_bounded_int(
            values[CROWDFUNDING_GRACE_KEY], DEFAULT_CROWDFUNDING_GRACE_DAYS, 0, MAX_CROWDFUNDING_GRACE_DAYS
        ),
    )


def save_reference_settings(database: Database, value: ReferenceSettings) -> ReferenceSettings:
    if value.min_votes < MIN_VOTES_MINIMUM:
        raise BggReferenceError(f"min_votes must be at least {MIN_VOTES_MINIMUM}")
    if not 0 <= value.min_wishing <= MAX_MIN_WISHING:
        raise BggReferenceError(f"min_wishing must be between 0 and {MAX_MIN_WISHING}")
    if not 0 <= value.daily_budget <= MAX_DAILY_BUDGET:
        raise BggReferenceError(f"daily_budget must be between 0 and {MAX_DAILY_BUDGET}")
    if not 0 <= value.crowdfunding_grace_days <= MAX_CROWDFUNDING_GRACE_DAYS:
        raise BggReferenceError(
            f"crowdfunding_grace_days must be between 0 and {MAX_CROWDFUNDING_GRACE_DAYS}"
        )
    AppSettingsStore(database).set_many(
        {
            MIN_VOTES_KEY: (str(value.min_votes), False),
            INCLUDE_EXPANSIONS_KEY: ("1" if value.include_expansions else "0", False),
            MIN_WISHING_KEY: (str(value.min_wishing), False),
            DAILY_BUDGET_KEY: (str(value.daily_budget), False),
            CROWDFUNDING_GRACE_KEY: (str(value.crowdfunding_grace_days), False),
        }
    )
    return load_reference_settings(database)


def get_sync_state(database: Database, key: str) -> str | None:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT value FROM bgg_reference_sync_state WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else None


def set_sync_state(database: Database, key: str, value: str) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO bgg_reference_sync_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, datetime.now(UTC).isoformat()),
        )


@dataclass(frozen=True)
class DumpRow:
    bgg_id: int
    name: str
    year_published: int | None
    rank: int | None
    bayes_average: float | None
    average: float | None
    users_rated: int
    is_expansion: int


@dataclass(frozen=True)
class DumpImportResult:
    source_filename: str
    sha256: str
    row_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    rejected_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_ranks_dump(payload: bytes) -> tuple[list[DumpRow], int]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BggReferenceError("BGG ranks dump must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise BggReferenceError("Dump has no header row")
    header = {name.strip().lower() for name in reader.fieldnames if name}
    missing = DUMP_REQUIRED_COLUMNS - header
    if missing:
        raise BggReferenceError(f"Missing required dump columns: {', '.join(sorted(missing))}")

    rows: list[DumpRow] = []
    seen: set[int] = set()
    rejected = 0
    for source_row in reader:
        row = {(key or "").strip().lower(): value for key, value in source_row.items() if key}
        bgg_id = _to_int(row.get("id"))
        name = _blank_to_none(row.get("name"))
        users_rated = _to_int(row.get("usersrated"))
        expansion = _blank_to_none(row.get("is_expansion"))
        if (
            bgg_id is None
            or bgg_id <= 0
            or bgg_id in seen
            or name is None
            or users_rated is None
            or users_rated < 0
            or expansion not in {"0", "1"}
        ):
            rejected += 1
            continue
        seen.add(bgg_id)
        rank = _to_int(row.get("rank"))
        rows.append(
            DumpRow(
                bgg_id=bgg_id,
                name=name,
                year_published=_to_int(row.get("yearpublished")) or None,
                rank=rank if rank and rank > 0 else None,
                bayes_average=_to_float(row.get("bayesaverage")) or None,
                average=_to_float(row.get("average")) or None,
                users_rated=users_rated,
                is_expansion=int(expansion),
            )
        )

    if not rows:
        raise BggReferenceError("Dump contains no valid rows")
    return rows, rejected


IMPORT_BATCH_SIZE = 5000

_DUMP_UPSERT_SQL = """
    INSERT INTO bgg_reference_games (
        bgg_id, name, year_published, is_expansion, rank,
        bayes_average, average, users_rated, source,
        dump_imported_at, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'dump', ?, ?, ?)
    ON CONFLICT(bgg_id) DO UPDATE SET
        name = excluded.name,
        year_published = excluded.year_published,
        is_expansion = excluded.is_expansion,
        rank = excluded.rank,
        bayes_average = excluded.bayes_average,
        average = excluded.average,
        users_rated = excluded.users_rated,
        dump_imported_at = excluded.dump_imported_at,
        updated_at = excluded.updated_at
    WHERE bgg_reference_games.api_checked_at IS NULL
      AND (
        bgg_reference_games.name IS NOT excluded.name
        OR bgg_reference_games.year_published IS NOT excluded.year_published
        OR bgg_reference_games.is_expansion IS NOT excluded.is_expansion
        OR bgg_reference_games.rank IS NOT excluded.rank
        OR bgg_reference_games.bayes_average IS NOT excluded.bayes_average
        OR bgg_reference_games.average IS NOT excluded.average
        OR bgg_reference_games.users_rated IS NOT excluded.users_rated
      )
"""


def _dump_params(row: DumpRow, now: str) -> tuple[object, ...]:
    return (
        row.bgg_id,
        row.name,
        row.year_published,
        row.is_expansion,
        row.rank,
        row.bayes_average,
        row.average,
        row.users_rated,
        now,
        now,
        now,
    )


class BggReferenceImporter:
    """Imports the BGG ranks dump into the reference catalog.

    Rows already refreshed through XML API2 are left untouched: the dump is
    only a bootstrap source and is older than any API observation.
    """

    def __init__(self, database: Database):
        self.database = database

    def import_bytes(self, payload: bytes, source_filename: str) -> DumpImportResult:
        digest = hashlib.sha256(payload).hexdigest()
        rows, rejected = parse_ranks_dump(payload)
        now = datetime.now(UTC).isoformat()
        created = updated = 0

        with self.database.connect() as connection:
            existing = {
                int(row["bgg_id"])
                for row in connection.execute("SELECT bgg_id FROM bgg_reference_games")
            }

        # Short write transactions: a single one over ~180k rows held the
        # SQLite write lock long enough to starve the other workers.
        for start in range(0, len(rows), IMPORT_BATCH_SIZE):
            batch = rows[start : start + IMPORT_BATCH_SIZE]
            with self.database.transaction(immediate=True) as connection:
                for row in batch:
                    cursor = connection.execute(_DUMP_UPSERT_SQL, _dump_params(row, now))
                    if row.bgg_id not in existing:
                        created += 1
                    elif cursor.rowcount:
                        updated += 1

        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO import_runs (
                    source_type, source_filename, sha256, row_count,
                    created_count, updated_count, unchanged_count, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DUMP_SOURCE_TYPE,
                    source_filename,
                    digest,
                    len(rows),
                    created,
                    updated,
                    len(rows) - created - updated,
                    now,
                ),
            )

        return DumpImportResult(
            source_filename=source_filename,
            sha256=digest,
            row_count=len(rows),
            created_count=created,
            updated_count=updated,
            unchanged_count=len(rows) - created - updated,
            rejected_count=rejected,
        )

    def import_path(self, path: Path) -> DumpImportResult:
        return self.import_bytes(path.read_bytes(), path.name)

    def import_if_changed(self, import_dir: Path) -> DumpImportResult | None:
        """Imports the dump found in the import folder once per file version.

        The file is never moved or deleted. A cheap size/mtime signature avoids
        rehashing an unchanged file; a content hash already recorded in
        import_runs is never imported twice.
        """
        path = import_dir / DUMP_DEFAULT_FILENAME
        if not path.is_file():
            return None
        stat = path.stat()
        signature = f"{stat.st_size}:{stat.st_mtime_ns}"
        if self._state(DUMP_WATCH_STATE_KEY) == signature:
            return None
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        with self.database.connect() as connection:
            already = connection.execute(
                "SELECT 1 FROM import_runs WHERE source_type = ? AND sha256 = ? LIMIT 1",
                (DUMP_SOURCE_TYPE, digest),
            ).fetchone()
        result = None if already else self.import_bytes(payload, path.name)
        self._set_state(DUMP_WATCH_STATE_KEY, signature)
        return result

    def _state(self, key: str) -> str | None:
        return get_sync_state(self.database, key)

    def _set_state(self, key: str, value: str) -> None:
        set_sync_state(self.database, key, value)


def _fts_query(query: str) -> str | None:
    tokens = normalize_title_text(query).split()
    if not tokens:
        return None
    return " ".join(f'"{token}"*' for token in tokens)


_VISIBLE_SQL = """
    g.removed_at IS NULL
    AND (
        g.users_rated >= :min_votes
        OR (
            g.admission_reason IS NOT NULL
            AND (g.admission_until IS NULL OR g.admission_until > :now)
        )
    )
    AND (:include_expansions = 1 OR g.is_expansion = 0)
"""


def _visibility_params(value: ReferenceSettings) -> dict[str, Any]:
    return {
        "min_votes": value.min_votes,
        "include_expansions": 1 if value.include_expansions else 0,
        "now": datetime.now(UTC).isoformat(),
    }


BROWSE_SORT_SQL = {
    "rank": "(g.rank IS NULL OR g.rank = 0), g.rank, g.users_rated DESC, g.bgg_id",
    "votes": "g.users_rated DESC, g.bgg_id",
    "rating": "(g.average IS NULL), g.average DESC, g.users_rated DESC, g.bgg_id",
    "newest": "(g.year_published IS NULL), g.year_published DESC, g.users_rated DESC, g.bgg_id",
    "title": "g.name COLLATE NOCASE, g.bgg_id",
}


# Cached rows are (bgg_id, name, year_published, rank, average, users_rated, is_expansion).
BROWSE_SORT_KEYS = {
    "rank": lambda r: (not r[3], r[3] or 0, -r[5], r[0]),
    "votes": lambda r: (-r[5], r[0]),
    "rating": lambda r: (r[4] is None, -(r[4] or 0), -r[5], r[0]),
    "newest": lambda r: (r[2] is None, -(r[2] or 0), -r[5], r[0]),
    "title": lambda r: (str(r[1]).casefold(), r[0]),
}
BROWSE_CACHE_SECONDS = 300
# Esplora reads every stored /thing (hundreds of MB): kept longer and
# refreshed in the background rather than on a user request.
EXPLORE_CACHE_SECONDS = 900
_browse_cache_lock = threading.Lock()
_browse_cache: dict[tuple[str, int, bool], dict[str, Any]] = {}


_explore_cache: dict[tuple[str, int, bool], dict[str, Any]] = {}
# One scan at a time: a request arriving during the startup scan waits for it.
_explore_build_lock = threading.Lock()


def clear_browse_cache() -> None:
    with _browse_cache_lock:
        _browse_cache.clear()
        _explore_cache.clear()


_POLL_RESULT_RE = re.compile(r'<result\b[^>]*?value="([^"]*)"[^>]*?numvotes="(\d+)"')


def _language_from_poll_xml(snippet: str | None) -> str | None:
    """Winner of the language dependence poll from a slice of the stored /thing XML.

    Rows fetched before the poll was parsed only keep it inside ``raw_xml``.
    """
    if not snippet:
        return None
    body = snippet.split("</poll>", 1)[0]
    best: tuple[int, str] | None = None
    for value, votes in _POLL_RESULT_RE.findall(body):
        if int(votes) > 0 and (best is None or int(votes) > best[0]):
            best = (int(votes), html.unescape(value).strip())
    return best[1] if best else None


_EXPLORE_FIELDS = (
    "min_players", "max_players", "playing_time", "min_play_time", "max_play_time",
    "bgg_average_weight", "bgg_recommended_age", "bgg_best_players",
    "bgg_recommended_players", "bgg_language_dependence", "categories", "mechanics",
)
# The poll inside raw_xml, as it appears in the JSON-escaped text.
_LANGUAGE_POLL_MARK = 'name=\\"language_dependence\\"'


def _names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := str(item).strip()) and len(text) <= 500]


# Card facts: the local library row wins, then the stored /thing details.
_ITEM_SELECT = """
    SELECT g.bgg_id, g.name, g.year_published, g.is_expansion,
           g.rank, g.average, g.users_rated, g.thumbnail_url, g.image_url,
           g.admission_reason, b.id AS board_game_id,
           COALESCE(b.min_players, json_extract(g.details_json, '$.min_players')) AS min_players,
           COALESCE(b.max_players, json_extract(g.details_json, '$.max_players')) AS max_players,
           COALESCE(b.playing_time, json_extract(g.details_json, '$.playing_time')) AS playing_time,
           COALESCE(b.min_play_time, json_extract(g.details_json, '$.min_play_time')) AS min_play_time,
           COALESCE(b.max_play_time, json_extract(g.details_json, '$.max_play_time')) AS max_play_time,
           COALESCE(b.bgg_average_weight, json_extract(g.details_json, '$.bgg_average_weight')) AS average_weight,
           COALESCE(b.bgg_recommended_age, json_extract(g.details_json, '$.bgg_recommended_age')) AS recommended_age,
           EXISTS(
               SELECT 1 FROM collection_entries c WHERE c.board_game_id = b.id AND c.own = 1
           ) AS owned
"""


def _reference_item(row: Any) -> dict[str, Any]:
    keys = row.keys()
    extra: dict[str, Any] = {}
    if "owned" in keys:
        extra = {
            "owned": bool(row["owned"]),
            "players": {"min": row["min_players"], "max": row["max_players"]},
            "play_time": {
                "playing": row["playing_time"],
                "min": row["min_play_time"],
                "max": row["max_play_time"],
            },
            "average_weight": row["average_weight"],
            "recommended_age": row["recommended_age"],
        }
    return {
        **extra,
        "bgg_id": int(row["bgg_id"]),
        "name": row["name"],
        "year_published": row["year_published"],
        "is_expansion": bool(row["is_expansion"]),
        "rank": row["rank"],
        "average": row["average"],
        "users_rated": int(row["users_rated"]),
        "thumbnail_url": row["thumbnail_url"],
        "image_url": row["image_url"],
        "admission_reason": row["admission_reason"] or "votes",
        "in_catalog": row["board_game_id"] is not None,
    }


class BggReferenceCatalog:
    def __init__(self, database: Database):
        self.database = database

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        reference_settings: ReferenceSettings | None = None,
    ) -> list[dict[str, Any]]:
        match = _fts_query(query)
        if match is None:
            return []
        value = reference_settings or load_reference_settings(self.database)
        params = {
            **_visibility_params(value),
            "match": match,
            "exact": query.strip(),
            "limit": limit,
        }
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {_ITEM_SELECT}
                FROM bgg_reference_games_fts f
                JOIN bgg_reference_games g ON g.bgg_id = f.rowid
                LEFT JOIN board_games b ON b.bgg_id = g.bgg_id
                WHERE bgg_reference_games_fts MATCH :match
                  AND {_VISIBLE_SQL}
                ORDER BY (g.name = :exact COLLATE NOCASE) DESC,
                         g.users_rated DESC, g.bgg_id
                LIMIT :limit
                """,
                params,
            ).fetchall()
        return [_reference_item(row) for row in rows]

    def browse(
        self,
        *,
        query: str | None = None,
        sort: str = "rank",
        limit: int = 48,
        offset: int = 0,
        item_type: str | None = None,
        reference_settings: ReferenceSettings | None = None,
        allowed_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        """Paginated listing of the visible reference titles, optionally filtered by title and type.

        ``allowed_ids`` restricts the listing to the titles matched by the
        advanced filters (computed from ``explore_rows``).
        """
        value = reference_settings or load_reference_settings(self.database)
        sort = sort if sort in BROWSE_SORT_SQL else "rank"
        expansion = {"standalone": 0, "expansion": 1}.get(item_type or "")
        page = {"sort": sort, "limit": limit, "offset": offset}
        text = (query or "").strip()
        if not text:
            ordered = self._browse_order(value, sort, expansion)
            if allowed_ids is not None:
                ordered = [bgg_id for bgg_id in ordered if bgg_id in allowed_ids]
            ids = ordered[offset : offset + limit]
            return {"items": self._items_by_id(ids), "total": len(ordered), **page}
        match = _fts_query(text)
        if match is None:
            return {"items": [], "total": 0, **page}
        params = {
            **_visibility_params(value),
            "match": match,
            "limit": limit,
            "offset": offset,
            "expansion": expansion,
        }
        source = "bgg_reference_games_fts f JOIN bgg_reference_games g ON g.bgg_id = f.rowid"
        where = (
            f"bgg_reference_games_fts MATCH :match AND {_VISIBLE_SQL}"
            " AND (:expansion IS NULL OR g.is_expansion = :expansion)"
        )
        if allowed_ids is not None:
            with self.database.connect() as connection:
                matched = [
                    int(row[0])
                    for row in connection.execute(
                        f"SELECT g.bgg_id FROM {source} WHERE {where} ORDER BY {BROWSE_SORT_SQL[sort]}",
                        params,
                    ).fetchall()
                    if int(row[0]) in allowed_ids
                ]
            ids = matched[offset : offset + limit]
            return {"items": self._items_by_id(ids), "total": len(matched), **page}
        with self.database.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM {source} WHERE {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                {_ITEM_SELECT}
                FROM {source}
                LEFT JOIN board_games b ON b.bgg_id = g.bgg_id
                WHERE {where}
                ORDER BY {BROWSE_SORT_SQL[sort]}
                LIMIT :limit OFFSET :offset
                """,
                params,
            ).fetchall()
        return {"items": [_reference_item(row) for row in rows], "total": int(total), **page}

    def _browse_order(
        self, value: ReferenceSettings, sort: str, expansion: int | None = None
    ) -> list[int]:
        # The visibility columns sit after details_json, so filtering the whole
        # table walks every overflow page. One scan of the sort keys is cached
        # briefly and shared by all sort orders; pages are then read by key.
        key = (str(self.database.path), value.min_votes, value.include_expansions)
        now = time.monotonic()
        with _browse_cache_lock:
            entry = _browse_cache.get(key)
            if entry is None or now - entry["at"] > BROWSE_CACHE_SECONDS:
                entry = None
        if entry is None:
            with self.database.connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT g.bgg_id, g.name, g.year_published, g.rank, g.average,
                           g.users_rated, g.is_expansion
                    FROM bgg_reference_games g
                    WHERE {_VISIBLE_SQL}
                    """,
                    _visibility_params(value),
                ).fetchall()
            entry = {"at": now, "rows": [tuple(row) for row in rows], "orders": {}}
            with _browse_cache_lock:
                _browse_cache[key] = entry
        orders = entry["orders"]
        order_key = (sort, expansion)
        if order_key not in orders:
            rows = entry["rows"]
            if expansion is not None:
                rows = [row for row in rows if int(row[6]) == expansion]
            orders[order_key] = [row[0] for row in sorted(rows, key=BROWSE_SORT_KEYS[sort])]
        return orders[order_key]

    def _items_by_id(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {_ITEM_SELECT}
                FROM bgg_reference_games g
                LEFT JOIN board_games b ON b.bgg_id = g.bgg_id
                WHERE g.bgg_id IN ({placeholders}) AND g.removed_at IS NULL
                """,
                ids,
            ).fetchall()
        by_id = {int(row["bgg_id"]): _reference_item(row) for row in rows}
        return [by_id[bgg_id] for bgg_id in ids if bgg_id in by_id]

    def explore_rows(
        self,
        reference_settings: ReferenceSettings | None = None,
        *,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Visible base games with the facts Esplora filters on, cached briefly.

        Rows are shaped like library rows (same column names) so the explore
        filters can treat both sources alike. Titles never fetched from the
        API have no categories or mechanics but still match plain filters.
        """
        value = reference_settings or load_reference_settings(self.database)
        key = (str(self.database.path), value.min_votes, value.include_expansions)
        with _browse_cache_lock:
            entry = _explore_cache.get(key)
            stale = entry is not None and time.monotonic() - entry["at"] > EXPLORE_CACHE_SECONDS
            if stale and not entry.get("refreshing"):
                entry["refreshing"] = True
                threading.Thread(
                    target=self._refresh_explore_rows, args=(value, key), daemon=True
                ).start()
        if entry is not None and not refresh:
            # A stale scan is still served while the refresh runs in the background.
            return entry["rows"]
        with _explore_build_lock:
            if not refresh:
                with _browse_cache_lock:
                    entry = _explore_cache.get(key)
                if entry is not None:
                    return entry["rows"]
            return self._build_explore_rows(value, key)

    def _refresh_explore_rows(self, value: ReferenceSettings, key: tuple[str, int, bool]) -> None:
        try:
            with _explore_build_lock:
                self._build_explore_rows(value, key)
        except Exception:
            LOGGER.exception("BGG reference explore scan failed")
            with _browse_cache_lock:
                entry = _explore_cache.get(key)
                if entry is not None:
                    entry["refreshing"] = False

    def _build_explore_rows(
        self, value: ReferenceSettings, key: tuple[str, int, bool]
    ) -> list[dict[str, Any]]:
        now = time.monotonic()
        # One JSON parse per row: json_extract with several paths returns an
        # array. Older rows keep the language poll only inside raw_xml, which
        # is sliced from the stored text without parsing it.
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT g.bgg_id, g.name, g.year_published, g.rank,
                       g.bayes_average, g.average, g.users_rated,
                       g.thumbnail_url, g.image_url, g.admission_reason,
                       CASE WHEN g.description IS NOT NULL AND trim(g.description) != '' THEN 1 ELSE 0 END AS has_description,
                       json_extract(g.details_json, {", ".join(f"'$.{field}'" for field in _EXPLORE_FIELDS)}) AS facts,
                       substr(g.details_json, NULLIF(instr(g.details_json, :poll_mark), 0), 3000)
                           AS language_poll
                FROM bgg_reference_games g
                WHERE {_VISIBLE_SQL} AND g.is_expansion = 0
                """,
                {**_visibility_params(value), "poll_mark": _LANGUAGE_POLL_MARK},
            ).fetchall()
        result = []
        for row in rows:
            try:
                facts = dict(zip(_EXPLORE_FIELDS, json.loads(row["facts"] or "[]")))
            except ValueError:
                facts = {}
            average = row["average"] if row["average"] and row["average"] > 0 else None
            result.append(
                {
                    "bgg_id": int(row["bgg_id"]),
                    "name": row["name"],
                    "year_published": row["year_published"],
                    "rank": row["rank"],
                    "bgg_rank": row["rank"],
                    "bgg_bayes_average": row["bayes_average"],
                    "bgg_average": average,
                    "average": row["average"],
                    "users_rated": int(row["users_rated"] or 0),
                    "thumbnail_url": row["thumbnail_url"],
                    "image_url": row["image_url"],
                    "cover_url": row["image_url"] or row["thumbnail_url"],
                    "has_description": bool(row["has_description"]),
                    "admission_reason": row["admission_reason"],
                    "min_players": facts.get("min_players"),
                    "max_players": facts.get("max_players"),
                    "playing_time": facts.get("playing_time"),
                    "min_play_time": facts.get("min_play_time"),
                    "max_play_time": facts.get("max_play_time"),
                    "bgg_average_weight": facts.get("bgg_average_weight"),
                    "bgg_recommended_age": facts.get("bgg_recommended_age"),
                    "bgg_best_players": facts.get("bgg_best_players"),
                    "bgg_recommended_players": facts.get("bgg_recommended_players"),
                    "bgg_language_dependence": (
                        facts.get("bgg_language_dependence")
                        or _language_from_poll_xml(
                            (row["language_poll"] or "").replace('\\"', '"')
                        )
                    ),
                    "categories": _names(facts.get("categories")),
                    "mechanics": _names(facts.get("mechanics")),
                }
            )
        with _browse_cache_lock:
            _explore_cache[key] = {"at": now, "rows": result}
        return result

    def assistant_candidates(
        self,
        *,
        scan: int = 800,
        reference_settings: ReferenceSettings | None = None,
    ) -> list[dict[str, Any]]:
        """Best-ranked visible base games not owned, shaped like Catalog.assistant_candidates.

        Only the top ``scan`` titles by BGG rank are read, so the stored /thing
        details are parsed for a bounded set of rows.
        """
        value = reference_settings or load_reference_settings(self.database)
        ids = self._browse_order(value, "rank", 0)[: max(1, scan)]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT g.bgg_id, g.name, g.rank, g.average, g.details_json
                FROM bgg_reference_games g
                LEFT JOIN board_games b ON b.bgg_id = g.bgg_id
                WHERE g.bgg_id IN ({placeholders})
                  AND NOT EXISTS (
                      SELECT 1 FROM collection_entries c
                      WHERE c.board_game_id = b.id AND c.own = 1
                  )
                """,
                ids,
            ).fetchall()
        by_id: dict[int, dict[str, Any]] = {}
        for row in rows:
            try:
                details = json.loads(row["details_json"] or "{}")
            except ValueError:
                details = {}
            by_id[int(row["bgg_id"])] = {
                "bgg_id": int(row["bgg_id"]),
                "title": row["name"],
                "owned": False,
                "players": {"min": details.get("min_players"), "max": details.get("max_players")},
                "recommended_players": details.get("bgg_recommended_players"),
                "best_players": details.get("bgg_best_players"),
                "min_age": details.get("bgg_recommended_age"),
                "minutes": {
                    "playing": details.get("playing_time"),
                    "min": details.get("min_play_time"),
                    "max": details.get("max_play_time"),
                },
                "weight": details.get("bgg_average_weight"),
                "rating": row["average"],
                "rank": row["rank"],
                "categories": [str(item) for item in details.get("categories") or []],
                "mechanics": [str(item) for item in details.get("mechanics") or []],
            }
        return [by_id[bgg_id] for bgg_id in ids if bgg_id in by_id]

    def match_campaign_title(self, title: str, *, since_year: int) -> int | None:
        """Fail-closed campaign link: the normalized title must equal the name or an
        alternate title of exactly one recent or unpublished reference title."""
        target = normalize_title_text(title)
        match = _fts_query(title)
        if not target or match is None:
            return None
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id, g.name, g.alt_names
                FROM bgg_reference_games_fts f
                JOIN bgg_reference_games g ON g.bgg_id = f.rowid
                WHERE bgg_reference_games_fts MATCH :match
                  AND g.removed_at IS NULL
                  AND (g.year_published IS NULL OR g.year_published >= :since_year)
                """,
                {"match": match, "since_year": since_year},
            ).fetchall()
        found = {
            int(row["bgg_id"])
            for row in rows
            if target
            in {normalize_title_text(name) for name in [row["name"], *(row["alt_names"] or "").split("\n")]}
        }
        return found.pop() if len(found) == 1 else None

    def detail(self, bgg_id: int, client: Any | None = None) -> dict[str, Any] | None:
        """Reference row plus API details, fetching one /thing if never queried.

        Provider failures never hide the dump data: they are reported in
        ``detail_error`` and the call still succeeds.
        """
        row = self._detail_row(bgg_id)
        if row is None:
            return None
        detail_error = None
        if row["api_checked_at"] is None:
            if client is None:
                detail_error = "no_token"
            else:
                try:
                    metadata, raw_xml = client.thing_with_xml(bgg_id)
                except Exception as exc:  # network, XML or rate-limit failures
                    detail_error = f"{type(exc).__name__}: {exc}"[:300]
                else:
                    self.store_api_detail(bgg_id, metadata, raw_xml)
                    row = self._detail_row(bgg_id)
        try:
            details = json.loads(row["details_json"] or "{}")
        except ValueError:
            details = {}
        details.pop("raw_xml", None)
        details.pop(REFERENCE_TRANSLATION_KEY, None)
        return {
            "bgg_id": int(row["bgg_id"]),
            "name": row["name"],
            "year_published": row["year_published"],
            "is_expansion": bool(row["is_expansion"]),
            "rank": row["rank"] or None,
            "average": row["average"] or None,
            "users_rated": int(row["users_rated"]),
            "wishing": row["wishing"],
            "thumbnail_url": row["thumbnail_url"],
            "image_url": row["image_url"],
            "description": row["description"],
            "alternate_names": [n for n in (row["alt_names"] or "").split("\n") if n],
            "details": details,
            "api_checked_at": row["api_checked_at"],
            "detail_error": detail_error,
            "in_catalog": row["board_game_id"] is not None,
            "owned": bool(row["owned"]),
        }

    def _detail_row(self, bgg_id: int) -> Any:
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT g.*, b.id AS board_game_id,
                       EXISTS(
                           SELECT 1 FROM collection_entries c
                           WHERE c.board_game_id = b.id AND c.own = 1
                       ) AS owned
                FROM bgg_reference_games g
                LEFT JOIN board_games b ON b.bgg_id = g.bgg_id
                WHERE g.bgg_id = ? AND g.removed_at IS NULL
                """,
                (bgg_id,),
            ).fetchone()

    def store_api_detail(self, bgg_id: int, metadata: dict[str, Any], raw_xml: str) -> None:
        now = datetime.now(UTC).isoformat()
        alt_names = "\n".join(metadata.get("alternate_titles") or [])
        with self.database.connect() as connection:
            previous = connection.execute(
                "SELECT details_json FROM bgg_reference_games WHERE bgg_id = ?", (bgg_id,)
            ).fetchone()
            details: dict[str, Any] = {**metadata, "raw_xml": raw_xml}
            if previous is not None:
                kept = json.loads(previous["details_json"] or "{}").get(REFERENCE_TRANSLATION_KEY)
                if kept is not None:
                    details[REFERENCE_TRANSLATION_KEY] = kept
            connection.execute(
                """
                UPDATE bgg_reference_games SET
                    rank = COALESCE(?, rank),
                    bayes_average = COALESCE(?, bayes_average),
                    average = COALESCE(?, average),
                    users_rated = COALESCE(?, users_rated),
                    wishing = ?, owned_count = ?,
                    thumbnail_url = ?, image_url = ?, description = ?,
                    alt_names = ?, details_json = ?,
                    source = 'api', api_checked_at = ?, updated_at = ?, removed_at = NULL
                WHERE bgg_id = ?
                """,
                (
                    metadata.get("bgg_rank"),
                    metadata.get("bgg_bayes_average"),
                    metadata.get("bgg_average"),
                    metadata.get("bgg_users_rated"),
                    metadata.get("bgg_wishing"),
                    metadata.get("bgg_num_owned"),
                    metadata.get("thumbnail_url"),
                    metadata.get("cover_url"),
                    metadata.get("description"),
                    alt_names,
                    json.dumps(details, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                    bgg_id,
                ),
            )

    def add_to_collection(self, bgg_id: int) -> dict[str, Any]:
        """Promote a reference title into board_games as an owned collection entry.

        Idempotent: an existing board game or collection entry is never overwritten.
        """
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            reference = connection.execute(
                """
                SELECT bgg_id, name, year_published, is_expansion, rank,
                       bayes_average, average
                FROM bgg_reference_games
                WHERE bgg_id = ? AND removed_at IS NULL
                """,
                (bgg_id,),
            ).fetchone()
            board = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id = ?", (bgg_id,)
            ).fetchone()
            if reference is None and board is None:
                raise BggReferenceError(f"BGG #{bgg_id} is not in the reference catalog")
            created_game = board is None
            if board is None:
                cursor = connection.execute(
                    """
                    INSERT INTO board_games(
                        bgg_id, title, year_published, item_type, bgg_average,
                        bgg_bayes_average, bgg_rank, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bgg_id,
                        reference["name"],
                        reference["year_published"],
                        "expansion" if reference["is_expansion"] else "standalone",
                        reference["average"] or None,
                        reference["bayes_average"] or None,
                        reference["rank"] or None,
                        now,
                        now,
                    ),
                )
                board_game_id = int(cursor.lastrowid)
            else:
                board_game_id = int(board["id"])
            entry = connection.execute(
                "SELECT id FROM collection_entries WHERE board_game_id = ? LIMIT 1",
                (board_game_id,),
            ).fetchone()
            created_entry = entry is None
            if entry is None:
                connection.execute(
                    """
                    INSERT INTO collection_entries(
                        board_game_id, own, first_seen_at, created_at, updated_at
                    ) VALUES (?, 1, ?, ?, ?)
                    """,
                    (board_game_id, now, now, now),
                )
        return {
            "bgg_id": bgg_id,
            "board_game_id": board_game_id,
            "created_game": created_game,
            "created_entry": created_entry,
        }

    def status(self, reference_settings: ReferenceSettings | None = None) -> dict[str, Any]:
        value = reference_settings or load_reference_settings(self.database)
        with self.database.connect() as connection:
            totals = connection.execute(
                f"""
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN {_VISIBLE_SQL} THEN 1 ELSE 0 END), 0) AS visible,
                       COALESCE(SUM(CASE WHEN g.api_checked_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS api_checked
                FROM bgg_reference_games g
                """,
                _visibility_params(value),
            ).fetchone()
            last_import = connection.execute(
                """
                SELECT source_filename, sha256, row_count, created_count,
                       updated_count, unchanged_count, imported_at
                FROM import_runs
                WHERE source_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (DUMP_SOURCE_TYPE,),
            ).fetchone()
        return {
            "settings": value.to_dict(),
            "total": int(totals["total"]),
            "visible": int(totals["visible"]),
            "api_checked": int(totals["api_checked"]),
            "last_dump_import": dict(last_import) if last_import else None,
        }
