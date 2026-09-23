from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from boardgamecompanion.database import Database
from boardgamecompanion.documents import (
    DocumentError,
    DocumentStore,
    DocumentTooLarge,
    InvalidPdf,
)
from boardgamecompanion.rulebook_fetch import (
    RulebookFetcher,
    RulebookFetchPolicy,
    RulebookFetchResult,
)
from boardgamecompanion.rulebook_review import (
    RulebookReviewCorruptRecord,
    RulebookReviewQueue,
    candidate_from_snapshot,
)

MIN_INTERVAL_SECONDS = 3600
MAX_INTERVAL_SECONDS = 365 * 24 * 60 * 60
DEFAULT_INTERVAL_SECONDS = 30 * 24 * 60 * 60
DEFAULT_RETRY_BASE_SECONDS = 6 * 60 * 60
DEFAULT_RETRY_MAX_SECONDS = 7 * 24 * 60 * 60
DEFAULT_LEASE_SECONDS = 15 * 60
MAX_FAILURE_MESSAGE_LENGTH = 1000


class RulebookUpdateError(ValueError):
    pass


class RulebookUpdateNotFound(RulebookUpdateError):
    pass


class RulebookUpdateNotApproved(RulebookUpdateError):
    pass


class RulebookUpdateBusy(RulebookUpdateError):
    pass


class RulebookUpdateConflict(RulebookUpdateError):
    pass


class RulebookUpdateOutcome(StrEnum):
    CREATED = "created"
    UNCHANGED = "unchanged"
    FAILED = "failed"


FetcherFactory = Callable[[], RulebookFetcher]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime:
    current = value or _utcnow()
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _clean_failure_message(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return text[:MAX_FAILURE_MESSAGE_LENGTH]


def _row_to_target(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "review_item_id": row["review_item_id"],
        "bgg_id": row["bgg_id"],
        "game_title": row["game_title"],
        "review_status": row["review_status"],
        "enabled": bool(row["enabled"]),
        "interval_seconds": int(row["interval_seconds"]),
        "next_check_at": row["next_check_at"],
        "last_checked_at": row["last_checked_at"],
        "last_success_at": row["last_success_at"],
        "last_document_id": row["last_document_id"],
        "last_sha256": row["last_sha256"],
        "consecutive_failures": int(row["consecutive_failures"]),
        "last_outcome": row["last_outcome"],
        "last_failure_code": row["last_failure_code"],
        "last_failure_message": row["last_failure_message"],
        "leased": row["lease_owner"] is not None,
        "lease_until": row["lease_until"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    try:
        metadata = json.loads(row["http_metadata_json"] or "{}")
    except (TypeError, ValueError, RecursionError):
        metadata = {}
    try:
        redirects = json.loads(row["redirect_chain_json"] or "[]")
    except (TypeError, ValueError, RecursionError):
        redirects = []
    return {
        "id": row["id"],
        "target_id": row["target_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "outcome": row["outcome"],
        "document_id": row["document_id"],
        "sha256": row["sha256"],
        "requested_url": row["requested_url"],
        "final_url": row["final_url"],
        "status_code": row["status_code"],
        "byte_size": int(row["byte_size"]),
        "failure_code": row["failure_code"],
        "failure_message": row["failure_message"],
        "http_metadata": metadata,
        "redirect_chain": redirects,
    }


class RulebookUpdateService:
    def __init__(
        self,
        database: Database,
        manuals_dir: Path,
        *,
        fetcher_factory: FetcherFactory | None = None,
        default_interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        retry_base_seconds: int = DEFAULT_RETRY_BASE_SECONDS,
        retry_max_seconds: int = DEFAULT_RETRY_MAX_SECONDS,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_archive_bytes: int = 100 * 1024 * 1024,
        fetch_max_bytes: int = 32 * 1024 * 1024,
    ):
        self.database = database
        self.manuals_dir = Path(manuals_dir)
        self.default_interval_seconds = self._validate_interval(
            default_interval_seconds
        )
        if retry_base_seconds <= 0:
            raise ValueError("retry_base_seconds must be positive")
        if retry_max_seconds < retry_base_seconds:
            raise ValueError("retry_max_seconds must be >= retry_base_seconds")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if max_archive_bytes <= 0 or fetch_max_bytes <= 0:
            raise ValueError("document byte limits must be positive")
        self.retry_base_seconds = int(retry_base_seconds)
        self.retry_max_seconds = int(retry_max_seconds)
        self.lease_seconds = int(lease_seconds)
        self.max_archive_bytes = int(max_archive_bytes)
        self.fetch_max_bytes = min(int(fetch_max_bytes), self.max_archive_bytes)
        self._fetcher_factory = fetcher_factory or self._default_fetcher

    @staticmethod
    def _validate_interval(value: int) -> int:
        interval = int(value)
        if not MIN_INTERVAL_SECONDS <= interval <= MAX_INTERVAL_SECONDS:
            raise RulebookUpdateError(
                f"interval_seconds must be between {MIN_INTERVAL_SECONDS} "
                f"and {MAX_INTERVAL_SECONDS}"
            )
        return interval

    @staticmethod
    def _target_select(where: str = "1 = 1") -> str:
        return f"""
            SELECT
                t.*,
                g.bgg_id,
                g.title AS game_title,
                r.status AS review_status
            FROM rulebook_update_targets t
            JOIN board_games g ON g.id = t.board_game_id
            JOIN rulebook_review_items r ON r.id = t.review_item_id
            WHERE {where}
        """

    def _default_fetcher(self) -> RulebookFetcher:
        return RulebookFetcher(
            manuals_dir=self.manuals_dir,
            policy=RulebookFetchPolicy(max_bytes=self.fetch_max_bytes),
        )

    def _validated_target_item(self, row: sqlite3.Row) -> dict[str, Any]:
        item = _row_to_target(row)
        review = RulebookReviewQueue(self.database).get(row["review_item_id"])
        if review is None:
            raise RulebookUpdateNotFound(
                f"Rulebook review {row['review_item_id']} not found"
            )
        candidate = review["candidate"]
        item.update(
            {
                "provider": candidate["provider"],
                "source_kind": candidate["source_kind"],
                "url": candidate["url"],
                "review_status": review["status"],
            }
        )
        return item

    def ensure_target(
        self,
        review_item_id: str,
        *,
        interval_seconds: int | None = None,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]:
        interval = self._validate_interval(
            interval_seconds
            if interval_seconds is not None
            else self.default_interval_seconds
        )
        review = RulebookReviewQueue(self.database).get(review_item_id)
        if review is None:
            raise RulebookUpdateNotFound(
                f"Rulebook review {review_item_id} not found"
            )
        if review["status"] != "approved":
            raise RulebookUpdateNotApproved(
                f"Rulebook review {review_item_id} is not approved"
            )

        current = _as_utc(now)
        current_iso = _iso(current)
        target_id = str(uuid4())

        with self.database.transaction(immediate=True) as connection:
            review_row = connection.execute(
                """
                SELECT id, board_game_id, status
                FROM rulebook_review_items
                WHERE id = ?
                """,
                (review_item_id,),
            ).fetchone()
            if review_row is None:
                raise RulebookUpdateNotFound(
                    f"Rulebook review {review_item_id} not found"
                )
            if review_row["status"] != "approved":
                raise RulebookUpdateNotApproved(
                    f"Rulebook review {review_item_id} is not approved"
                )

            inserted = connection.execute(
                """
                INSERT INTO rulebook_update_targets (
                    id, review_item_id, board_game_id, enabled,
                    interval_seconds, next_check_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(review_item_id) DO NOTHING
                """,
                (
                    target_id,
                    review_item_id,
                    review_row["board_game_id"],
                    interval,
                    current_iso,
                    current_iso,
                    current_iso,
                ),
            )
            created = inserted.rowcount == 1
            row = connection.execute(
                self._target_select(
                    "t.id = ?" if created else "t.review_item_id = ?"
                ),
                (target_id if created else review_item_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(
                    "Rulebook update target insert completed without a readable row"
                )
        return _row_to_target(row), created

    def synchronize_approved_targets(
        self,
        *,
        limit: int = 500,
        now: datetime | None = None,
    ) -> dict[str, int]:
        if not 1 <= int(limit) <= 5000:
            raise RulebookUpdateError("sync limit must be between 1 and 5000")
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT r.id
                FROM rulebook_review_items r
                LEFT JOIN rulebook_update_targets t
                    ON t.review_item_id = r.id
                WHERE r.status = 'approved' AND t.id IS NULL
                ORDER BY r.decided_at, r.id
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        created = 0
        corrupt = 0
        for row in rows:
            try:
                _, was_created = self.ensure_target(
                    row["id"],
                    now=now,
                )
            except RulebookReviewCorruptRecord:
                corrupt += 1
                continue
            created += int(was_created)
        return {
            "discovered": len(rows),
            "created": created,
            "corrupt": corrupt,
        }

    def get_target(self, review_item_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                self._target_select("t.review_item_id = ?"),
                (review_item_id,),
            ).fetchone()
        return self._validated_target_item(row) if row else None

    def list_targets(
        self,
        *,
        enabled: bool | None = None,
        bgg_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not 1 <= int(limit) <= 250:
            raise RulebookUpdateError("limit must be between 1 and 250")
        if int(offset) < 0:
            raise RulebookUpdateError("offset must be non-negative")

        clauses: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            clauses.append("t.enabled = ?")
            params.append(1 if enabled else 0)
        if bgg_id is not None:
            clauses.append("g.bgg_id = ?")
            params.append(int(bgg_id))
        where = " AND ".join(clauses) if clauses else "1 = 1"

        with self.database.connect() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM rulebook_update_targets t
                JOIN board_games g ON g.id = t.board_game_id
                WHERE {where}
                """,
                params,
            ).fetchone()["count"]
            rows = connection.execute(
                self._target_select(where)
                + """
                ORDER BY t.next_check_at, t.id
                LIMIT ? OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        items: list[dict[str, Any]] = []
        corrupt_items: list[dict[str, str]] = []
        for row in rows:
            try:
                items.append(self._validated_target_item(row))
            except RulebookReviewCorruptRecord:
                corrupt_items.append(
                    {
                        "review_item_id": row["review_item_id"],
                        "error": "corrupt persisted review record",
                    }
                )

        return {
            "total": int(total),
            "limit": int(limit),
            "offset": int(offset),
            "items": items,
            "corrupt_count": len(corrupt_items),
            "corrupt_items": corrupt_items,
        }

    def configure_target(
        self,
        review_item_id: str,
        *,
        enabled: bool | None = None,
        interval_seconds: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        target, _ = self.ensure_target(review_item_id, now=now)
        interval = (
            self._validate_interval(interval_seconds)
            if interval_seconds is not None
            else None
        )
        current_iso = _iso(_as_utc(now))
        assignments = ["updated_at = ?"]
        params: list[Any] = [current_iso]
        if enabled is not None:
            assignments.append("enabled = ?")
            params.append(1 if enabled else 0)
        if interval is not None:
            assignments.append("interval_seconds = ?")
            params.append(interval)
        params.append(target["id"])

        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                f"""
                UPDATE rulebook_update_targets
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                params,
            )
            row = connection.execute(
                self._target_select("t.id = ?"),
                (target["id"],),
            ).fetchone()
            assert row is not None
        return _row_to_target(row)

    def list_runs(
        self,
        review_item_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        target = self.get_target(review_item_id)
        if target is None:
            raise RulebookUpdateNotFound(
                f"Update target for review {review_item_id} not found"
            )
        if not 1 <= int(limit) <= 250 or int(offset) < 0:
            raise RulebookUpdateError("Invalid run pagination")
        with self.database.connect() as connection:
            total = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM rulebook_update_runs
                WHERE target_id = ?
                """,
                (target["id"],),
            ).fetchone()["count"]
            rows = connection.execute(
                """
                SELECT *
                FROM rulebook_update_runs
                WHERE target_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (target["id"], int(limit), int(offset)),
            ).fetchall()
        return {
            "total": int(total),
            "limit": int(limit),
            "offset": int(offset),
            "items": [_row_to_run(row) for row in rows],
        }

    def claim_due(
        self,
        *,
        owner: str,
        limit: int = 10,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if not owner.strip():
            raise RulebookUpdateError("Lease owner must not be empty")
        if not 1 <= int(limit) <= 100:
            raise RulebookUpdateError("claim limit must be between 1 and 100")
        current = _as_utc(now)
        current_iso = _iso(current)
        lease_until = _iso(current + timedelta(seconds=self.lease_seconds))

        with self.database.transaction(immediate=True) as connection:
            rows = connection.execute(
                """
                SELECT t.id
                FROM rulebook_update_targets t
                JOIN rulebook_review_items r
                    ON r.id = t.review_item_id
                WHERE t.enabled = 1
                  AND r.status = 'approved'
                  AND t.next_check_at <= ?
                  AND (t.lease_until IS NULL OR t.lease_until <= ?)
                ORDER BY t.next_check_at, t.id
                LIMIT ?
                """,
                (current_iso, current_iso, int(limit)),
            ).fetchall()
            ids = [row["id"] for row in rows]
            for target_id in ids:
                connection.execute(
                    """
                    UPDATE rulebook_update_targets
                    SET lease_owner = ?, lease_until = ?, updated_at = ?
                    WHERE id = ?
                      AND (lease_until IS NULL OR lease_until <= ?)
                    """,
                    (owner, lease_until, current_iso, target_id, current_iso),
                )
            claimed: list[dict[str, Any]] = []
            for target_id in ids:
                row = connection.execute(
                    self._target_select(
                        "t.id = ? AND t.lease_owner = ?"
                    ),
                    (target_id, owner),
                ).fetchone()
                if row is not None:
                    claimed.append(_row_to_target(row))
        return claimed

    def _claim_review_target(
        self,
        review_item_id: str,
        *,
        owner: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        target, _ = self.ensure_target(review_item_id, now=now)
        current = _as_utc(now)
        current_iso = _iso(current)
        lease_until = _iso(current + timedelta(seconds=self.lease_seconds))

        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                self._target_select("t.id = ?"),
                (target["id"],),
            ).fetchone()
            if row is None:
                raise RulebookUpdateNotFound(
                    f"Update target for review {review_item_id} not found"
                )
            active_until = _parse_iso(row["lease_until"])
            if active_until is not None and active_until > current:
                raise RulebookUpdateBusy(
                    f"Update target for review {review_item_id} is already running"
                )
            connection.execute(
                """
                UPDATE rulebook_update_targets
                SET lease_owner = ?, lease_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (owner, lease_until, current_iso, target["id"]),
            )
            row = connection.execute(
                self._target_select("t.id = ?"),
                (target["id"],),
            ).fetchone()
            assert row is not None
        return _row_to_target(row)

    def run_review_now(
        self,
        review_item_id: str,
        *,
        owner: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        lease_owner = owner or f"manual-{uuid4()}"
        target = self._claim_review_target(
            review_item_id,
            owner=lease_owner,
            now=now,
        )
        return self._execute_leased(
            target["id"],
            owner=lease_owner,
            started_at=_as_utc(now),
        )

    def run_due(
        self,
        *,
        limit: int = 10,
        owner: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not 1 <= int(limit) <= 100:
            raise RulebookUpdateError("run limit must be between 1 and 100")
        lease_owner = owner or f"worker-{uuid4()}"
        sync = self.synchronize_approved_targets(now=now)
        results: list[dict[str, Any]] = []

        for _ in range(int(limit)):
            claimed = self.claim_due(
                owner=lease_owner,
                limit=1,
                now=now,
            )
            if not claimed:
                break
            target = claimed[0]
            results.append(
                self._execute_leased(
                    target["id"],
                    owner=lease_owner,
                    started_at=_as_utc(now),
                )
            )

        return {
            "synchronized": sync,
            "claimed": len(results),
            "results": results,
        }

    def _execute_leased(
        self,
        target_id: str,
        *,
        owner: str,
        started_at: datetime,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            target_row = connection.execute(
                self._target_select("t.id = ?"),
                (target_id,),
            ).fetchone()
        if target_row is None:
            raise RulebookUpdateNotFound(
                f"Rulebook update target {target_id} not found"
            )
        if target_row["lease_owner"] != owner:
            raise RulebookUpdateConflict("Rulebook update lease ownership changed")

        review = RulebookReviewQueue(self.database).get(
            target_row["review_item_id"]
        )
        if review is None:
            raise RulebookUpdateNotFound(
                f"Rulebook review {target_row['review_item_id']} not found"
            )
        if review["status"] != "approved":
            raise RulebookUpdateNotApproved(
                f"Rulebook review {review['id']} is no longer approved"
            )
        candidate = candidate_from_snapshot(review["candidate"])

        fetcher = self._fetcher_factory()
        result = fetcher.fetch(candidate)
        finished_at = _utcnow()

        if not result.ok:
            failure_code = (
                result.failure.code.value
                if result.failure is not None
                else "fetch_failed"
            )
            failure_message = (
                result.failure.message
                if result.failure is not None
                else "Rulebook fetch failed"
            )
            return self._finalize_failure(
                target_row,
                owner=owner,
                started_at=started_at,
                finished_at=finished_at,
                result=result,
                failure_code=failure_code,
                failure_message=failure_message,
            )

        if result.local_path is None or result.sha256 is None:
            return self._finalize_failure(
                target_row,
                owner=owner,
                started_at=started_at,
                finished_at=finished_at,
                result=result,
                failure_code="fetch_result_invalid",
                failure_message="Successful fetch did not provide a persisted PDF",
            )

        provenance = {
            "ingest": "scheduled_rulebook_fetch",
            "review_item_id": review["id"],
            "candidate_key": review["candidate_key"],
            "decision_source": review["decision_source"],
            "candidate_confidence": candidate.confidence,
            "requested_url": result.requested_url,
            "final_url": result.final_url,
            "redirect_chain": [
                {
                    "status_code": hop.status_code,
                    "from_url": hop.from_url,
                    "to_url": hop.to_url,
                }
                for hop in result.redirect_chain
            ],
            "http_status": result.status_code,
            "http_metadata": dict(result.http_metadata),
            "fetched_at": _iso(finished_at),
        }

        try:
            document, created = DocumentStore(
                self.database,
                self.manuals_dir,
            ).archive_fetched_pdf(
                bgg_id=int(review["bgg_id"]),
                source_path=Path(result.local_path),
                expected_sha256=result.sha256,
                expected_size_bytes=result.byte_size,
                original_filename=self._filename_for_result(result),
                document_type=candidate.document_type,
                language=candidate.language,
                title=candidate.title,
                version_label=candidate.version_label,
                edition=candidate.edition,
                source_kind=candidate.source_kind.value,
                source_provider=candidate.provider,
                source_url=result.requested_url,
                is_official=candidate.official,
                provenance=provenance,
                max_bytes=self.max_archive_bytes,
            )
        except (DocumentError, DocumentTooLarge, InvalidPdf, OSError, sqlite3.Error) as exc:
            return self._finalize_failure(
                target_row,
                owner=owner,
                started_at=started_at,
                finished_at=_utcnow(),
                result=result,
                failure_code="archive_error",
                failure_message=str(exc) or exc.__class__.__name__,
            )

        outcome = (
            RulebookUpdateOutcome.CREATED
            if created
            else RulebookUpdateOutcome.UNCHANGED
        )
        return self._finalize_success(
            target_row,
            owner=owner,
            started_at=started_at,
            finished_at=_utcnow(),
            result=result,
            document=document,
            outcome=outcome,
        )

    @staticmethod
    def _filename_for_result(result: RulebookFetchResult) -> str:
        raw = ""
        if result.final_url:
            raw = unquote(urlsplit(result.final_url).path.rsplit("/", 1)[-1])
        raw = Path(raw or "rulebook.pdf").name
        if not raw.lower().endswith(".pdf"):
            raw = f"{raw or 'rulebook'}.pdf"
        return raw[:255]

    def _retry_delay(self, failure_count: int) -> int:
        exponent = max(0, min(int(failure_count) - 1, 20))
        return min(
            self.retry_base_seconds * (2**exponent),
            self.retry_max_seconds,
        )

    def _finalize_failure(
        self,
        target_row: sqlite3.Row,
        *,
        owner: str,
        started_at: datetime,
        finished_at: datetime,
        result: RulebookFetchResult,
        failure_code: str,
        failure_message: str,
    ) -> dict[str, Any]:
        failures = int(target_row["consecutive_failures"]) + 1
        next_check = finished_at + timedelta(
            seconds=self._retry_delay(failures)
        )
        run_id = str(uuid4())
        message = _clean_failure_message(failure_message)
        code = str(failure_code)[:100]
        self._persist_completion(
            target_id=target_row["id"],
            owner=owner,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            outcome=RulebookUpdateOutcome.FAILED,
            document_id=None,
            sha256=None,
            result=result,
            failure_code=code,
            failure_message=message,
            next_check_at=next_check,
            consecutive_failures=failures,
        )
        return {
            "target_id": target_row["id"],
            "review_item_id": target_row["review_item_id"],
            "run_id": run_id,
            "outcome": RulebookUpdateOutcome.FAILED.value,
            "failure_code": code,
            "failure_message": message,
            "next_check_at": _iso(next_check),
        }

    def _finalize_success(
        self,
        target_row: sqlite3.Row,
        *,
        owner: str,
        started_at: datetime,
        finished_at: datetime,
        result: RulebookFetchResult,
        document: dict[str, Any],
        outcome: RulebookUpdateOutcome,
    ) -> dict[str, Any]:
        run_id = str(uuid4())
        next_check = self._persist_completion(
            target_id=target_row["id"],
            owner=owner,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            document_id=document["id"],
            sha256=result.sha256,
            result=result,
            failure_code=None,
            failure_message=None,
            next_check_at=None,
            consecutive_failures=0,
        )
        return {
            "target_id": target_row["id"],
            "review_item_id": target_row["review_item_id"],
            "run_id": run_id,
            "outcome": outcome.value,
            "document": document,
            "next_check_at": _iso(next_check),
        }

    def _persist_completion(
        self,
        *,
        target_id: str,
        owner: str,
        run_id: str,
        started_at: datetime,
        finished_at: datetime,
        outcome: RulebookUpdateOutcome,
        document_id: str | None,
        sha256: str | None,
        result: RulebookFetchResult,
        failure_code: str | None,
        failure_message: str | None,
        next_check_at: datetime | None,
        consecutive_failures: int,
    ) -> datetime:
        metadata = json.dumps(
            dict(result.http_metadata),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        redirects = json.dumps(
            [
                {
                    "status_code": hop.status_code,
                    "from_url": hop.from_url,
                    "to_url": hop.to_url,
                }
                for hop in result.redirect_chain
            ],
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        finished_iso = _iso(finished_at)

        with self.database.transaction(immediate=True) as connection:
            target = connection.execute(
                "SELECT * FROM rulebook_update_targets WHERE id = ?",
                (target_id,),
            ).fetchone()
            if target is None:
                raise RulebookUpdateNotFound(
                    f"Rulebook update target {target_id} not found"
                )
            if target["lease_owner"] != owner:
                raise RulebookUpdateConflict(
                    "Rulebook update lease ownership changed before completion"
                )

            if outcome is RulebookUpdateOutcome.FAILED:
                if next_check_at is None:
                    raise RuntimeError("Failed update completion is missing retry time")
                effective_next_check = next_check_at
            else:
                effective_next_check = finished_at + timedelta(
                    seconds=int(target["interval_seconds"])
                )

            connection.execute(
                """
                INSERT INTO rulebook_update_runs (
                    id, target_id, started_at, finished_at, outcome,
                    document_id, sha256, requested_url, final_url,
                    status_code, byte_size, failure_code, failure_message,
                    http_metadata_json, redirect_chain_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    target_id,
                    _iso(started_at),
                    finished_iso,
                    outcome.value,
                    document_id,
                    sha256,
                    result.requested_url,
                    result.final_url,
                    result.status_code,
                    int(result.byte_size),
                    failure_code,
                    failure_message,
                    metadata,
                    redirects,
                ),
            )

            if outcome is RulebookUpdateOutcome.FAILED:
                connection.execute(
                    """
                    UPDATE rulebook_update_targets
                    SET next_check_at = ?,
                        last_checked_at = ?,
                        consecutive_failures = ?,
                        last_outcome = 'failed',
                        last_failure_code = ?,
                        last_failure_message = ?,
                        lease_owner = NULL,
                        lease_until = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        _iso(effective_next_check),
                        finished_iso,
                        int(consecutive_failures),
                        failure_code,
                        failure_message,
                        finished_iso,
                        target_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE rulebook_update_targets
                    SET next_check_at = ?,
                        last_checked_at = ?,
                        last_success_at = ?,
                        last_document_id = ?,
                        last_sha256 = ?,
                        consecutive_failures = 0,
                        last_outcome = ?,
                        last_failure_code = NULL,
                        last_failure_message = NULL,
                        lease_owner = NULL,
                        lease_until = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        _iso(effective_next_check),
                        finished_iso,
                        finished_iso,
                        document_id,
                        sha256,
                        outcome.value,
                        finished_iso,
                        target_id,
                    ),
                )

        return effective_next_check
