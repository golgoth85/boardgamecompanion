from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from boardgamecompanion.database import Database
from boardgamecompanion.rulebooks import (
    OFFICIAL_SOURCES,
    RulebookCandidate,
)

UNATTENDED_MIN_CONFIDENCE = 95
DEFAULT_UNATTENDED_LANGUAGES = ("it", "en")
MAX_CANDIDATE_SNAPSHOT_BYTES = 256 * 1024


class RulebookReviewError(ValueError):
    pass


class RulebookReviewNotFound(RulebookReviewError):
    pass


class RulebookReviewConflict(RulebookReviewError):
    pass


class RulebookReviewCandidateMismatch(RulebookReviewError):
    pass


class RulebookReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RulebookReviewEvaluation:
    unattended: bool
    reasons: tuple[str, ...]

    @property
    def action(self) -> str:
        return "unattended" if self.unattended else "review"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def candidate_snapshot(candidate: RulebookCandidate) -> dict[str, Any]:
    return {
        "provider": candidate.provider,
        "source_kind": candidate.source_kind.value,
        "url": candidate.url,
        "language": candidate.language,
        "document_type": candidate.document_type,
        "official": candidate.official,
        "confidence": candidate.confidence,
        "title": candidate.title,
        "version_label": candidate.version_label,
        "edition": candidate.edition,
        "bgg_id": candidate.bgg_id,
        "game_title": candidate.game_title,
        "year": candidate.year,
        "publisher": candidate.publisher,
        "metadata": _json_safe(candidate.metadata),
    }


def candidate_from_snapshot(snapshot: Mapping[str, Any]) -> RulebookCandidate:
    return RulebookCandidate(
        provider=snapshot["provider"],
        source_kind=snapshot["source_kind"],
        url=snapshot["url"],
        language=snapshot.get("language", "und"),
        document_type=snapshot.get("document_type", "rulebook"),
        official=snapshot.get("official", False),
        confidence=snapshot.get("confidence"),
        title=snapshot.get("title"),
        version_label=snapshot.get("version_label"),
        edition=snapshot.get("edition"),
        bgg_id=snapshot.get("bgg_id"),
        game_title=snapshot.get("game_title"),
        year=snapshot.get("year"),
        publisher=snapshot.get("publisher"),
        metadata=snapshot.get("metadata") or {},
    )


def _canonical_snapshot(candidate: RulebookCandidate) -> tuple[str, str]:
    snapshot = candidate_snapshot(candidate)
    serialized = json.dumps(
        snapshot,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    encoded = serialized.encode("utf-8")
    if len(encoded) > MAX_CANDIDATE_SNAPSHOT_BYTES:
        raise RulebookReviewError(
            f"Candidate snapshot exceeds {MAX_CANDIDATE_SNAPSHOT_BYTES} bytes"
        )
    key = hashlib.sha256(encoded).hexdigest()
    return serialized, key


def evaluate_candidate(
    candidate: RulebookCandidate,
    *,
    bgg_id: int,
    unattended_languages: tuple[str, ...] = DEFAULT_UNATTENDED_LANGUAGES,
) -> RulebookReviewEvaluation:
    if candidate.bgg_id is not None and candidate.bgg_id != bgg_id:
        raise RulebookReviewCandidateMismatch(
            f"Candidate BGG #{candidate.bgg_id} does not match game BGG #{bgg_id}"
        )

    reasons: list[str] = []
    eligible = True

    if candidate.source_kind in OFFICIAL_SOURCES and candidate.official:
        reasons.append("source:official")
    else:
        eligible = False
        reasons.append("review:unofficial-source")

    if int(candidate.confidence) >= UNATTENDED_MIN_CONFIDENCE:
        reasons.append(f"confidence:{candidate.confidence}")
    else:
        eligible = False
        reasons.append(f"review:confidence:{candidate.confidence}")

    if candidate.bgg_id == bgg_id:
        reasons.append("bgg_id:exact")
    else:
        eligible = False
        reasons.append("review:bgg-id-not-exact")
    language = candidate.language.split("-", 1)[0]
    allowed_languages = {
        value.strip().lower().split("-", 1)[0]
        for value in unattended_languages
        if value.strip()
    }
    if language in allowed_languages:
        reasons.append(f"language:{candidate.language}")
    else:
        eligible = False
        reasons.append(f"review:language:{candidate.language}")

    return RulebookReviewEvaluation(
        unattended=eligible,
        reasons=tuple(reasons),
    )


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    candidate = json.loads(row["candidate_json"])
    reasons = json.loads(row["policy_reasons_json"])
    return {
        "id": row["id"],
        "bgg_id": row["bgg_id"],
        "game_title": row["game_title"],
        "candidate_key": row["candidate_key"],
        "candidate": candidate,
        "policy_action": row["policy_action"],
        "policy_reasons": reasons,
        "status": row["status"],
        "decision_source": row["decision_source"],
        "decision_note": row["decision_note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "decided_at": row["decided_at"],
    }


class RulebookReviewQueue:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _select_sql(where: str = "1 = 1") -> str:
        return f"""
            SELECT r.*, g.bgg_id, g.title AS game_title
            FROM rulebook_review_items r
            JOIN board_games g ON g.id = r.board_game_id
            WHERE {where}
        """

    def submit(
        self,
        *,
        bgg_id: int,
        candidate: RulebookCandidate,
    ) -> tuple[dict[str, Any], bool]:
        evaluation = evaluate_candidate(candidate, bgg_id=bgg_id)
        serialized, candidate_key = _canonical_snapshot(candidate)
        now = datetime.now(UTC).isoformat()
        status = (
            RulebookReviewStatus.APPROVED
            if evaluation.unattended
            else RulebookReviewStatus.PENDING
        )
        decision_source = "policy" if evaluation.unattended else None
        decided_at = now if evaluation.unattended else None

        with self.database.transaction() as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id = ?",
                (bgg_id,),
            ).fetchone()
            if game is None:
                raise RulebookReviewNotFound(
                    f"Board game BGG #{bgg_id} not found"
                )

            item_id = str(uuid4())
            try:
                connection.execute(
                    """
                    INSERT INTO rulebook_review_items (
                        id, board_game_id, candidate_key, candidate_json,
                        provider, source_kind, url, language, document_type,
                        official, confidence, policy_action, policy_reasons_json,
                        status, decision_source, decision_note,
                        created_at, updated_at, decided_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                    """,
                    (
                        item_id,
                        game["id"],
                        candidate_key,
                        serialized,
                        candidate.provider,
                        candidate.source_kind.value,
                        candidate.url,
                        candidate.language,
                        candidate.document_type,
                        1 if candidate.official else 0,
                        int(candidate.confidence),
                        evaluation.action,
                        json.dumps(list(evaluation.reasons), separators=(",", ":")),
                        status.value,
                        decision_source,
                        now,
                        now,
                        decided_at,
                    ),
                )
                created = True
            except sqlite3.IntegrityError:
                existing = connection.execute(
                    self._select_sql(
                        "r.board_game_id = ? AND r.candidate_key = ?"
                    ),
                    (game["id"], candidate_key),
                ).fetchone()
                if existing is None:
                    raise
                return _row_to_item(existing), False

            row = connection.execute(
                self._select_sql("r.id = ?"),
                (item_id,),
            ).fetchone()
            assert row is not None
            return _row_to_item(row), created

    def get(self, review_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                self._select_sql("r.id = ?"),
                (review_id,),
            ).fetchone()
        return _row_to_item(row) if row else None

    def list(
        self,
        *,
        status: RulebookReviewStatus | str | None = None,
        bgg_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not 1 <= int(limit) <= 250:
            raise RulebookReviewError("limit must be between 1 and 250")
        if int(offset) < 0:
            raise RulebookReviewError("offset must be non-negative")

        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            try:
                normalized_status = RulebookReviewStatus(status).value
            except ValueError as exc:
                raise RulebookReviewError(
                    f"Unsupported review status: {status}"
                ) from exc
            clauses.append("r.status = ?")
            params.append(normalized_status)
        if bgg_id is not None:
            clauses.append("g.bgg_id = ?")
            params.append(int(bgg_id))
        where = " AND ".join(clauses) if clauses else "1 = 1"

        with self.database.connect() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM rulebook_review_items r
                JOIN board_games g ON g.id = r.board_game_id
                WHERE {where}
                """,
                params,
            ).fetchone()["count"]
            rows = connection.execute(
                self._select_sql(where)
                + """
                ORDER BY
                    CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                    r.created_at DESC,
                    r.id
                LIMIT ? OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()

        return {
            "total": int(total),
            "limit": int(limit),
            "offset": int(offset),
            "items": [_row_to_item(row) for row in rows],
        }

    def decide(
        self,
        review_id: str,
        *,
        decision: RulebookReviewStatus | str,
        note: str | None = None,
    ) -> dict[str, Any]:
        try:
            target = RulebookReviewStatus(decision)
        except ValueError as exc:
            raise RulebookReviewError(
                f"Unsupported review decision: {decision}"
            ) from exc
        if target is RulebookReviewStatus.PENDING:
            raise RulebookReviewError("Decision must be approved or rejected")

        clean_note = (note or "").strip() or None
        if clean_note is not None and len(clean_note) > 2000:
            raise RulebookReviewError("Decision note exceeds 2000 characters")
        now = datetime.now(UTC).isoformat()

        with self.database.transaction() as connection:
            updated = connection.execute(
                """
                UPDATE rulebook_review_items
                SET status = ?, decision_source = 'user',
                    decision_note = ?, decided_at = ?, updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (target.value, clean_note, now, now, review_id),
            )
            row = connection.execute(
                self._select_sql("r.id = ?"),
                (review_id,),
            ).fetchone()
            if row is None:
                raise RulebookReviewNotFound(
                    f"Rulebook review {review_id} not found"
                )
            if updated.rowcount == 1:
                return _row_to_item(row)
            if row["status"] == target.value:
                return _row_to_item(row)
            raise RulebookReviewConflict(
                f"Rulebook review {review_id} is already {row['status']}"
            )
