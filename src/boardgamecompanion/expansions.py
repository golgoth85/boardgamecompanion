from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from boardgamecompanion.bgg_metadata import BggApiClient, BggMetadataError
from boardgamecompanion.database import Database
from boardgamecompanion.notifications import NotificationService


_MINOR_RE = re.compile(
    r"\b("
    r"promo|promotional|miniature|miniatures|mini|token|tokens|dice|die|"
    r"sleeve|sleeves|playmat|play mat|organizer|storage|insert|upgrade|"
    r"component|components|coin|coins|marker|markers|terrain|resin|"
    r"poster|art ?book|soundtrack|pin|pins|card ?pack|deck ?box|"
    r"replacement|deluxe components|accessory|accessories"
    r")\b",
    re.I,
)
_CONTENT_RE = re.compile(
    r"\b(expansion|campaign|adventure|adventures|story|stories|"
    r"scenario|scenarios|quest|quests|chapter|season|chronicle|"
    r"new characters|new faction|faction|map|module|modules)\b",
    re.I,
)


def expansion_relevance(metadata: dict[str, Any]) -> tuple[bool, int, str]:
    title = str(metadata.get("title") or "").strip()
    if not title:
        return False, -10, "titolo assente"
    score = 0
    reasons: list[str] = []
    if _MINOR_RE.search(title):
        score -= 5
        reasons.append("accessorio/minor add-on")
    if _CONTENT_RE.search(title):
        score += 3
        reasons.append("contenuto espansione")
    owned = int(metadata.get("bgg_num_owned") or 0)
    if owned >= 1000:
        score += 3
        reasons.append("ampia diffusione BGG")
    elif owned >= 250:
        score += 2
        reasons.append("diffusione BGG")
    elif owned >= 75:
        score += 1
    weight = metadata.get("bgg_average_weight")
    if weight is not None:
        score += 1
    if len(title) > 15:
        score += 1
    relevant = score >= 2 and not (_MINOR_RE.search(title) and score < 4)
    return relevant, score, ", ".join(reasons) or "espansione BGG"


class ExpansionService:
    def __init__(
        self,
        database: Database,
        client: BggApiClient | None,
        *,
        refresh_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        self.database = database
        self.client = client
        self.refresh_seconds = int(refresh_seconds)

    def _parent(self, bgg_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT g.id,g.bgg_id,g.title,g.item_type,MAX(COALESCE(c.own,0)) AS owned
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                WHERE g.bgg_id=?
                GROUP BY g.id
                """,
                (int(bgg_id),),
            ).fetchone()
        if row is None:
            raise ValueError("Board game not found")
        return dict(row)

    def cached(self, bgg_id: int) -> dict[str, Any]:
        parent = self._parent(bgg_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT x.*,MAX(COALESCE(c.own,0)) AS owned
                FROM game_expansion_candidates x
                LEFT JOIN board_games g ON g.bgg_id=x.bgg_id
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                WHERE x.parent_board_game_id=?
                GROUP BY x.id
                ORDER BY owned DESC,x.year_published DESC,x.title COLLATE NOCASE
                """,
                (parent["id"],),
            ).fetchall()
            state = connection.execute(
                "SELECT * FROM expansion_scan_state WHERE parent_board_game_id=?",
                (parent["id"],),
            ).fetchone()
        return {
            "bgg_id": int(bgg_id),
            "items": [self._row(row) for row in rows],
            "last_scanned_at": state["last_scanned_at"] if state else None,
            "initialized": bool(state["initialized_at"]) if state else False,
            "available": self.client is not None,
        }

    @staticmethod
    def _row(row) -> dict[str, Any]:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        return {
            "bgg_id": int(row["bgg_id"]),
            "title": row["title"],
            "year_published": row["year_published"],
            "cover_url": row["cover_url"],
            "bgg_average": row["bgg_average"],
            "bgg_num_owned": row["bgg_num_owned"],
            "relevance_score": row["relevance_score"],
            "relevance_reason": row["relevance_reason"],
            "owned": bool(row["owned"]),
            "bgg_url": f"https://boardgamegeek.com/boardgame/{int(row['bgg_id'])}",
            "metadata": metadata if isinstance(metadata, dict) else {},
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
        }

    def refresh(self, bgg_id: int, *, force: bool = False) -> dict[str, Any]:
        parent = self._parent(bgg_id)
        cached = self.cached(bgg_id)
        if self.client is None:
            return cached
        if not force and cached["last_scanned_at"]:
            try:
                last = datetime.fromisoformat(str(cached["last_scanned_at"]).replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=UTC)
                if datetime.now(UTC) - last < timedelta(seconds=self.refresh_seconds):
                    return cached
            except ValueError:
                pass

        metadata = self.client.thing(int(bgg_id))
        raw_links = metadata.get("expansions")
        if not isinstance(raw_links, list):
            raw_links = []
        ids = [
            int(item["bgg_id"])
            for item in raw_links
            if isinstance(item, dict) and str(item.get("bgg_id") or "").isdigit()
        ]
        details: dict[int, dict[str, Any]] = {}
        for offset in range(0, len(ids), 20):
            details.update(self.client.things(ids[offset : offset + 20]))

        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            state = connection.execute(
                "SELECT initialized_at FROM expansion_scan_state WHERE parent_board_game_id=?",
                (parent["id"],),
            ).fetchone()
            was_initialized = bool(state and state["initialized_at"])
            owned_ids = {
                int(row["bgg_id"])
                for row in connection.execute(
                    """
                    SELECT DISTINCT g.bgg_id
                    FROM board_games g
                    JOIN collection_entries c ON c.board_game_id=g.id
                    WHERE c.own=1
                    """
                ).fetchall()
            }
            existing_ids = {
                int(row["bgg_id"])
                for row in connection.execute(
                    "SELECT bgg_id FROM game_expansion_candidates WHERE parent_board_game_id=?",
                    (parent["id"],),
                ).fetchall()
            }

        relevant: list[tuple[dict[str, Any], int, str]] = []
        for identifier in ids:
            item = details.get(identifier)
            if not item:
                continue
            keep, score, reason = expansion_relevance(item)
            if keep:
                relevant.append((item, score, reason))

        notifications = NotificationService(self.database)
        with self.database.transaction(immediate=True) as connection:
            for item, score, reason in relevant:
                identifier = int(item["bgg_id"])
                connection.execute(
                    """
                    INSERT INTO game_expansion_candidates(
                        parent_board_game_id,bgg_id,title,year_published,cover_url,
                        bgg_average,bgg_num_owned,relevance_score,relevance_reason,
                        metadata_json,first_seen_at,last_seen_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(parent_board_game_id,bgg_id) DO UPDATE SET
                        title=excluded.title,
                        year_published=excluded.year_published,
                        cover_url=excluded.cover_url,
                        bgg_average=excluded.bgg_average,
                        bgg_num_owned=excluded.bgg_num_owned,
                        relevance_score=excluded.relevance_score,
                        relevance_reason=excluded.relevance_reason,
                        metadata_json=excluded.metadata_json,
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        parent["id"],
                        identifier,
                        item.get("title"),
                        item.get("year_published"),
                        item.get("cover_url"),
                        item.get("bgg_average"),
                        item.get("bgg_num_owned"),
                        score,
                        reason,
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                        now,
                        now,
                    ),
                )
            initialized_at = state["initialized_at"] if state and state["initialized_at"] else now
            connection.execute(
                """
                INSERT INTO expansion_scan_state(
                    parent_board_game_id,last_scanned_at,initialized_at
                ) VALUES(?,?,?)
                ON CONFLICT(parent_board_game_id) DO UPDATE SET
                    last_scanned_at=excluded.last_scanned_at,
                    initialized_at=COALESCE(expansion_scan_state.initialized_at,excluded.initialized_at)
                """,
                (parent["id"], now, initialized_at),
            )

        if was_initialized:
            for item, _score, _reason in relevant:
                identifier = int(item["bgg_id"])
                if identifier in existing_ids or identifier in owned_ids:
                    continue
                notifications.create_once(
                    dedupe_key=f"expansion:{int(bgg_id)}:{identifier}",
                    category="expansion",
                    title=f"Nuova espansione: {item.get('title')}",
                    body=f"Nuova espansione rilevante per {parent['title']}.",
                    target_url=f"https://boardgamegeek.com/boardgame/{identifier}",
                    source={"parent_bgg_id": int(bgg_id), "expansion_bgg_id": identifier},
                )
        return self.cached(bgg_id)

    def refresh_stale_owned(self, *, limit: int = 6) -> dict[str, Any]:
        if self.client is None:
            return {"attempted": 0, "updated": 0, "errors": 0}
        threshold = (datetime.now(UTC) - timedelta(seconds=self.refresh_seconds)).isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT g.bgg_id
                FROM board_games g
                JOIN collection_entries c ON c.board_game_id=g.id AND c.own=1
                LEFT JOIN expansion_scan_state s ON s.parent_board_game_id=g.id
                WHERE COALESCE(g.item_type,'standalone')!='expansion'
                  AND (s.last_scanned_at IS NULL OR s.last_scanned_at<=?)
                ORDER BY s.last_scanned_at IS NOT NULL,s.last_scanned_at,g.title COLLATE NOCASE
                LIMIT ?
                """,
                (threshold, max(1, min(int(limit), 20))),
            ).fetchall()
        updated = 0
        errors = 0
        for row in rows:
            try:
                self.refresh(int(row["bgg_id"]), force=True)
                updated += 1
            except (BggMetadataError, ValueError):
                errors += 1
        return {"attempted": len(rows), "updated": updated, "errors": errors}
