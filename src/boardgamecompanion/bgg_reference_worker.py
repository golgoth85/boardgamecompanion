from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from boardgamecompanion.bgg_metadata import MAX_THING_IDS
from boardgamecompanion.bgg_reference import (
    BggReferenceCatalog,
    ReferenceSettings,
    get_sync_state,
    load_reference_settings,
    set_sync_state,
)
from boardgamecompanion.database import Database

LOGGER = logging.getLogger(__name__)

BUDGET_DAY_KEY = "budget_day"
BUDGET_USED_KEY = "budget_used"
NEW_IDS_DAY_KEY = "new_ids_day"
NEW_ID_CURSOR_KEY = "new_id_cursor"
LAST_ERROR_KEY = "worker_last_error"
LAST_RUN_KEY = "worker_last_run"

EMPTY_BATCHES_BEFORE_STOP = 3
CANDIDATE_RECHECK_DAYS = 7
ADMITTED_RECHECK_DAYS = 14
UPCOMING_ADMISSION_DAYS = 30
ACCEPTED_ITEM_TYPES = {"boardgame", "boardgameexpansion"}


class BggReferenceWorker:
    """Keeps the reference catalog fresh through XML API2 within a daily budget.

    Queues, in priority order: new IDs beyond the highest one seen, recent or
    unpublished titles below the vote threshold, and a rotation over visible
    titles. Without a token the catalog simply stays where it is.
    """

    def __init__(
        self,
        database: Database,
        client_factory: Callable[[], Any | None],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self._client_factory = client_factory
        self._now = now or (lambda: datetime.now(UTC))

    # -- budget -----------------------------------------------------------
    def _remaining_budget(self, limit: int) -> int:
        today = self._now().date().isoformat()
        if get_sync_state(self.database, BUDGET_DAY_KEY) != today:
            set_sync_state(self.database, BUDGET_DAY_KEY, today)
            set_sync_state(self.database, BUDGET_USED_KEY, "0")
        used = int(get_sync_state(self.database, BUDGET_USED_KEY) or 0)
        return max(0, limit - used)

    def _spend(self) -> None:
        used = int(get_sync_state(self.database, BUDGET_USED_KEY) or 0)
        set_sync_state(self.database, BUDGET_USED_KEY, str(used + 1))

    # -- entry point --------------------------------------------------------
    def run_once(self) -> dict[str, Any]:
        summary: dict[str, Any] = {"status": "ok", "requests": 0, "stored": 0, "new": 0, "removed": 0}
        reference = load_reference_settings(self.database)
        if reference.daily_budget <= 0:
            return {**summary, "status": "suspended"}
        client = self._client_factory()
        if client is None:
            return {**summary, "status": "no_token"}
        self._summary = summary
        self._client = client
        self._reference = reference
        self._catalog = BggReferenceCatalog(self.database)
        try:
            self._scan_new_ids()
            self._refresh_queue(self._candidate_ids, CANDIDATE_RECHECK_DAYS)
            self._refresh_queue(self._admitted_ids, ADMITTED_RECHECK_DAYS)
            set_sync_state(self.database, LAST_ERROR_KEY, "")
        except _BudgetExhausted:
            summary["status"] = "budget_exhausted"
        except Exception as exc:  # provider failures must not stop the app
            LOGGER.exception("BGG reference worker failed")
            summary["status"] = "error"
            set_sync_state(self.database, LAST_ERROR_KEY, f"{type(exc).__name__}: {exc}"[:300])
        set_sync_state(self.database, LAST_RUN_KEY, self._now().isoformat())
        return summary

    # -- requests -----------------------------------------------------------
    def _fetch(self, ids: list[int]) -> dict[int, tuple[dict[str, Any], str]]:
        if self._remaining_budget(self._reference.daily_budget) <= 0:
            raise _BudgetExhausted
        self._spend()
        self._summary["requests"] += 1
        return self._client.things_with_xml(ids)

    # -- new IDs ------------------------------------------------------------
    def _scan_new_ids(self) -> None:
        today = self._now().date().isoformat()
        if get_sync_state(self.database, NEW_IDS_DAY_KEY) == today:
            return
        with self.database.connect() as connection:
            highest = connection.execute("SELECT COALESCE(MAX(bgg_id), 0) FROM bgg_reference_games").fetchone()[0]
        cursor = max(int(get_sync_state(self.database, NEW_ID_CURSOR_KEY) or 0), int(highest))
        next_id = cursor + 1
        empty = 0
        while empty < EMPTY_BATCHES_BEFORE_STOP:
            ids = list(range(next_id, next_id + MAX_THING_IDS))
            items = self._fetch(ids)
            next_id += MAX_THING_IDS
            if not items:
                empty += 1
                continue
            empty = 0
            for bgg_id, (metadata, raw_xml) in sorted(items.items()):
                self._insert_new(bgg_id, metadata, raw_xml)
                cursor = max(cursor, bgg_id)
            set_sync_state(self.database, NEW_ID_CURSOR_KEY, str(cursor))
        # The cursor stays on the last real ID, so the empty tail is probed again tomorrow.
        set_sync_state(self.database, NEW_IDS_DAY_KEY, today)

    def _insert_new(self, bgg_id: int, metadata: dict[str, Any], raw_xml: str) -> None:
        if metadata.get("item_type") not in ACCEPTED_ITEM_TYPES:
            return
        now = self._now().isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO bgg_reference_games (
                    bgg_id, name, year_published, is_expansion, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'api', ?, ?)
                """,
                (
                    bgg_id,
                    metadata["title"],
                    metadata.get("year_published") or None,
                    1 if metadata.get("item_type") == "boardgameexpansion" else 0,
                    now,
                    now,
                ),
            )
        self._store(bgg_id, metadata, raw_xml, recheck_days=CANDIDATE_RECHECK_DAYS)
        self._summary["new"] += 1

    # -- refresh queues -----------------------------------------------------
    def _candidate_ids(self, limit: int) -> list[int]:
        """Recent or unpublished titles below the vote threshold, due for a check."""
        current_year = self._now().year
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT bgg_id FROM bgg_reference_games
                WHERE removed_at IS NULL AND users_rated < :min_votes
                  AND (year_published IS NULL OR year_published >= :recent)
                  AND (next_check_at IS NULL OR next_check_at <= :now)
                ORDER BY COALESCE(next_check_at, ''), bgg_id
                LIMIT :limit
                """,
                {
                    "min_votes": self._reference.min_votes,
                    "recent": current_year - 1,
                    "now": self._now().isoformat(),
                    "limit": limit,
                },
            ).fetchall()
        return [int(row["bgg_id"]) for row in rows]

    def _admitted_ids(self, limit: int) -> list[int]:
        """Titles above the threshold, rotated so every one is seen within 14 days."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT bgg_id FROM bgg_reference_games
                WHERE removed_at IS NULL AND users_rated >= :min_votes
                  AND (next_check_at IS NULL OR next_check_at <= :now)
                ORDER BY COALESCE(next_check_at, ''), users_rated DESC, bgg_id
                LIMIT :limit
                """,
                {
                    "min_votes": self._reference.min_votes,
                    "now": self._now().isoformat(),
                    "limit": limit,
                },
            ).fetchall()
        return [int(row["bgg_id"]) for row in rows]

    def _refresh_queue(self, select: Callable[[int], list[int]], recheck_days: int) -> None:
        while True:
            ids = select(MAX_THING_IDS)
            if not ids:
                return
            items = self._fetch(ids)
            for bgg_id in ids:
                if bgg_id in items:
                    metadata, raw_xml = items[bgg_id]
                    self._store(bgg_id, metadata, raw_xml, recheck_days=recheck_days)
                elif items:
                    self._mark_removed(bgg_id)
                else:
                    # An empty answer for existing IDs is more likely a hiccup than
                    # a mass removal: push the whole batch back instead of marking it.
                    self._postpone(bgg_id)

    # -- persistence --------------------------------------------------------
    def _store(self, bgg_id: int, metadata: dict[str, Any], raw_xml: str, *, recheck_days: int) -> None:
        self._catalog.store_api_detail(bgg_id, metadata, raw_xml)
        now = self._now()
        users_rated = metadata.get("bgg_users_rated") or 0
        wishing = metadata.get("bgg_wishing") or 0
        year = metadata.get("year_published") or None
        recent = year is None or year >= now.year - 1
        with self.database.transaction() as connection:
            if users_rated >= self._reference.min_votes:
                # Votes alone admit the title; any signal expiry no longer matters.
                connection.execute(
                    "UPDATE bgg_reference_games SET admission_reason = NULL, admission_until = NULL WHERE bgg_id = ?",
                    (bgg_id,),
                )
            elif recent and self._reference.min_wishing > 0 and wishing >= self._reference.min_wishing:
                # Never override a crowdfunding or hot admission.
                connection.execute(
                    """
                    UPDATE bgg_reference_games SET admission_reason = 'upcoming', admission_until = ?
                    WHERE bgg_id = ? AND (admission_reason IS NULL OR admission_reason = 'upcoming')
                    """,
                    ((now + timedelta(days=UPCOMING_ADMISSION_DAYS)).isoformat(), bgg_id),
                )
            connection.execute(
                "UPDATE bgg_reference_games SET next_check_at = ? WHERE bgg_id = ?",
                ((now + timedelta(days=recheck_days)).isoformat(), bgg_id),
            )
        self._summary["stored"] += 1

    def _mark_removed(self, bgg_id: int) -> None:
        now = self._now().isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE bgg_reference_games SET removed_at = ?, updated_at = ? WHERE bgg_id = ?",
                (now, now, bgg_id),
            )
        self._summary["removed"] += 1

    def _postpone(self, bgg_id: int) -> None:
        later = (self._now() + timedelta(hours=6)).isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE bgg_reference_games SET next_check_at = ? WHERE bgg_id = ?",
                (later, bgg_id),
            )


class _BudgetExhausted(Exception):
    pass


def worker_status(database: Database, reference: ReferenceSettings | None = None) -> dict[str, Any]:
    value = reference or load_reference_settings(database)
    return {
        "budget_day": get_sync_state(database, BUDGET_DAY_KEY),
        "budget_used": int(get_sync_state(database, BUDGET_USED_KEY) or 0),
        "daily_budget": value.daily_budget,
        "last_run": get_sync_state(database, LAST_RUN_KEY),
        "last_error": get_sync_state(database, LAST_ERROR_KEY) or None,
        "new_id_cursor": int(get_sync_state(database, NEW_ID_CURSOR_KEY) or 0),
    }
