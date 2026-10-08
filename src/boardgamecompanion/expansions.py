from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any

from boardgamecompanion.bgg_metadata import BggMetadataError, BggMetadataStore
from boardgamecompanion.database import Database
from boardgamecompanion.notifications import NotificationStore

_MINOR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpromo(?:tional)?\b", re.I), "promo"),
    (re.compile(r"\bminiatures?\b|\bminis?\b", re.I), "miniature"),
    (re.compile(r"\btoken(?:s)?\b|\bmarkers?\b", re.I), "tokens"),
    (re.compile(r"\bcoins?\b|\bmetal coins?\b", re.I), "coins"),
    (re.compile(r"\bplay\s?mats?\b|\bneoprene\b", re.I), "playmat"),
    (re.compile(r"\bsleeves?\b", re.I), "sleeves"),
    (re.compile(r"\bdice(?: set| pack)?\b", re.I), "dice"),
    (re.compile(r"\borganizer\b|\binsert\b|\bstorage\b", re.I), "storage"),
    (re.compile(r"\bupgrade (?:kit|pack|set)\b|\bcomponent upgrade\b", re.I), "upgrade"),
    (re.compile(r"\bacrylic\b|\bdeluxe components?\b", re.I), "components"),
    (re.compile(r"\bscenario (?:pack|set)\b", re.I), "scenario_pack"),
    (re.compile(r"\bcharacter (?:pack|set)\b|\bhero (?:pack|set)\b", re.I), "character_pack"),
    (re.compile(r"\bcard (?:pack|set)\b", re.I), "card_pack"),
    (re.compile(r"\bterrain (?:pack|set)\b|\bscenery\b", re.I), "terrain"),
    (re.compile(r"\breplacement\b|\bstickers?\b|\bpins?\b", re.I), "accessory"),
    (re.compile(r"\bart book\b|\bsoundtrack\b", re.I), "media"),
)


class ExpansionError(RuntimeError):
    pass


class ExpansionGameNotFound(ExpansionError):
    pass


def _normalized_title(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(text.casefold().split())


def minor_expansion_reason(title: str) -> str | None:
    normalized = _normalized_title(title)
    for pattern, reason in _MINOR_PATTERNS:
        if pattern.search(normalized):
            return reason
    return None


def is_relevant_expansion(title: str, metadata: dict[str, Any] | None = None) -> bool:
    if not str(title or "").strip():
        return False
    if minor_expansion_reason(title):
        return False
    if metadata:
        item_type = str(metadata.get("item_type") or "").strip()
        if item_type and item_type != "boardgameexpansion":
            return False
    return True


class ExpansionService:
    def __init__(
        self,
        database: Database,
        metadata_store: BggMetadataStore,
        *,
        refresh_seconds: int = 24 * 60 * 60,
    ) -> None:
        self.database = database
        self.metadata_store = metadata_store
        self.refresh_seconds = max(60 * 60, int(refresh_seconds))
        self.notifications = NotificationStore(database)

    def _base_game(self, bgg_id: int):
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT g.id,g.bgg_id,g.title,g.item_type,COALESCE(MAX(c.own),0) AS own
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                WHERE g.bgg_id=?
                GROUP BY g.id,g.bgg_id,g.title,g.item_type
                """,
                (int(bgg_id),),
            ).fetchone()
        if row is None:
            raise ExpansionGameNotFound(f"Board game BGG #{bgg_id} not found")
        return row

    def _base_metadata(
        self,
        bgg_id: int,
        *,
        refresh: bool,
    ) -> dict[str, Any] | None:
        cached = self.metadata_store.get(bgg_id)
        cached_metadata = (cached or {}).get("metadata") or {}
        has_expansion_field = "expansions" in cached_metadata
        if refresh or (not has_expansion_field and self.metadata_store.client is not None):
            try:
                return self.metadata_store.refresh(bgg_id, force=True)
            except BggMetadataError:
                if cached is not None:
                    return cached
                raise
        return cached

    @staticmethod
    def _linked_expansions(enrichment: dict[str, Any] | None) -> list[dict[str, Any]]:
        metadata = (enrichment or {}).get("metadata") or {}
        raw = metadata.get("expansions")
        if not isinstance(raw, list):
            return []
        result: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                bgg_id = int(item.get("bgg_id"))
            except (TypeError, ValueError):
                continue
            title = str(item.get("title") or "").strip()
            if bgg_id <= 0 or not title or bgg_id in seen:
                continue
            seen.add(bgg_id)
            result.append({"bgg_id": bgg_id, "title": title})
        return result

    def _owned_ids(self) -> set[int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT g.bgg_id
                FROM board_games g
                JOIN collection_entries c ON c.board_game_id=g.id
                WHERE COALESCE(c.own,0)=1
                """
            ).fetchall()
        return {int(row["bgg_id"]) for row in rows}

    def _cached_detail(self, bgg_id: int) -> dict[str, Any] | None:
        enrichment = self.metadata_store.get(bgg_id)
        if enrichment is None:
            return None
        return dict(enrichment.get("metadata") or {})

    def list_for_game(
        self,
        bgg_id: int,
        *,
        refresh: bool = False,
        fetch_details: bool = True,
    ) -> dict[str, Any]:
        base = self._base_game(bgg_id)
        enrichment = self._base_metadata(int(bgg_id), refresh=refresh)
        links = self._linked_expansions(enrichment)
        owned = self._owned_ids()

        relevant_links = [
            item for item in links if is_relevant_expansion(item["title"])
        ][:80]
        detail_by_id: dict[int, dict[str, Any]] = {}
        missing_detail: list[int] = []
        for item in relevant_links:
            identifier = int(item["bgg_id"])
            cached = self._cached_detail(identifier)
            if cached is not None:
                detail_by_id[identifier] = cached
            elif fetch_details and self.metadata_store.client is not None:
                missing_detail.append(identifier)

        if fetch_details and missing_detail and self.metadata_store.client is not None:
            for offset in range(0, len(missing_detail), 20):
                chunk = missing_detail[offset:offset + 20]
                try:
                    detail_by_id.update(self.metadata_store.client.things(chunk))
                except Exception:
                    continue

        items: list[dict[str, Any]] = []
        excluded_count = max(0, len(links) - len(relevant_links))
        for link in relevant_links:
            identifier = int(link["bgg_id"])
            detail = detail_by_id.get(identifier) or {}
            title = str(detail.get("title") or link["title"]).strip()
            if not is_relevant_expansion(title, detail):
                excluded_count += 1
                continue
            items.append(
                {
                    "bgg_id": identifier,
                    "title": title,
                    "year_published": detail.get("year_published"),
                    "cover_url": detail.get("cover_url"),
                    "owned": identifier in owned,
                    "bgg_average": detail.get("bgg_average"),
                    "bgg_num_owned": detail.get("bgg_num_owned"),
                    "url": f"https://boardgamegeek.com/boardgame/{identifier}",
                }
            )

        items.sort(
            key=lambda item: (
                bool(item["owned"]),
                -(int(item["year_published"]) if item.get("year_published") else 0),
                str(item["title"]).casefold(),
            )
        )
        return {
            "bgg_id": int(base["bgg_id"]),
            "title": base["title"],
            "configured": self.metadata_store.client is not None,
            "items": items,
            "missing_count": sum(1 for item in items if not item["owned"]),
            "owned_count": sum(1 for item in items if item["owned"]),
            "excluded_minor_count": excluded_count,
        }

    def scan_game(self, bgg_id: int) -> dict[str, Any]:
        base = self._base_game(bgg_id)
        if str(base["item_type"] or "standalone") == "expansion":
            return {"bgg_id": int(bgg_id), "skipped": "expansion"}
        current = datetime.now(UTC)
        try:
            enrichment = self._base_metadata(int(bgg_id), refresh=True)
            links = self._linked_expansions(enrichment)
        except Exception as exc:
            self._record_scan(
                int(base["id"]),
                current=current,
                error=str(exc)[:1000],
                baseline_complete=None,
            )
            raise

        with self.database.connect() as connection:
            scan = connection.execute(
                """
                SELECT baseline_complete
                FROM expansion_scan_state
                WHERE base_board_game_id=?
                """,
                (int(base["id"]),),
            ).fetchone()
            existing_rows = connection.execute(
                """
                SELECT expansion_bgg_id
                FROM expansion_watch_state
                WHERE base_board_game_id=?
                """,
                (int(base["id"]),),
            ).fetchall()
        baseline_complete = bool(scan and scan["baseline_complete"])
        existing = {int(row["expansion_bgg_id"]) for row in existing_rows}
        owned = self._owned_ids()
        new_relevant: list[dict[str, Any]] = []

        with self.database.transaction(immediate=True) as connection:
            for link in links:
                identifier = int(link["bgg_id"])
                title = str(link["title"])
                relevant = is_relevant_expansion(title)
                connection.execute(
                    """
                    INSERT INTO expansion_watch_state(
                        base_board_game_id,expansion_bgg_id,title,is_relevant,
                        first_seen_at,last_seen_at
                    ) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(base_board_game_id,expansion_bgg_id) DO UPDATE SET
                        title=excluded.title,
                        is_relevant=excluded.is_relevant,
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        int(base["id"]),
                        identifier,
                        title,
                        1 if relevant else 0,
                        current.isoformat(),
                        current.isoformat(),
                    ),
                )
                if (
                    baseline_complete
                    and relevant
                    and identifier not in existing
                    and identifier not in owned
                ):
                    new_relevant.append(link)

        for link in new_relevant:
            identifier = int(link["bgg_id"])
            self.notifications.create_once(
                category="expansion",
                dedupe_key=f"expansion:{int(base['bgg_id'])}:{identifier}",
                title=f"Nuova espansione per {base['title']}",
                body=str(link["title"]),
                target_url=f"/games/{int(base['bgg_id'])}?expansion={identifier}",
                related_bgg_id=int(base["bgg_id"]),
                metadata={
                    "expansion_bgg_id": identifier,
                    "expansion_title": link["title"],
                },
            )

        self._record_scan(
            int(base["id"]),
            current=current,
            error=None,
            baseline_complete=True,
        )
        return {
            "bgg_id": int(base["bgg_id"]),
            "linked_count": len(links),
            "new_relevant_count": len(new_relevant),
        }

    def _record_scan(
        self,
        board_game_id: int,
        *,
        current: datetime,
        error: str | None,
        baseline_complete: bool | None,
    ) -> None:
        current_iso = current.isoformat()
        next_iso = (current + timedelta(seconds=self.refresh_seconds)).isoformat()
        with self.database.transaction(immediate=True) as connection:
            existing = connection.execute(
                """
                SELECT baseline_complete
                FROM expansion_scan_state
                WHERE base_board_game_id=?
                """,
                (int(board_game_id),),
            ).fetchone()
            baseline = (
                int(bool(baseline_complete))
                if baseline_complete is not None
                else int(bool(existing and existing["baseline_complete"]))
            )
            connection.execute(
                """
                INSERT INTO expansion_scan_state(
                    base_board_game_id,baseline_complete,last_checked_at,
                    next_check_at,last_error
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(base_board_game_id) DO UPDATE SET
                    baseline_complete=excluded.baseline_complete,
                    last_checked_at=excluded.last_checked_at,
                    next_check_at=excluded.next_check_at,
                    last_error=excluded.last_error
                """,
                (
                    int(board_game_id),
                    baseline,
                    current_iso,
                    next_iso,
                    error,
                ),
            )

    def scan_due(self, *, limit: int = 4) -> dict[str, int]:
        current = datetime.now(UTC)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id
                FROM board_games g
                JOIN collection_entries c ON c.board_game_id=g.id
                LEFT JOIN expansion_scan_state s ON s.base_board_game_id=g.id
                WHERE COALESCE(c.own,0)=1
                  AND COALESCE(g.item_type,'standalone')!='expansion'
                  AND (s.next_check_at IS NULL OR s.next_check_at<=?)
                GROUP BY g.id,g.bgg_id,COALESCE(s.next_check_at,'')
                ORDER BY COALESCE(s.next_check_at,''),g.title COLLATE NOCASE
                LIMIT ?
                """,
                (current.isoformat(), max(1, min(int(limit), 20))),
            ).fetchall()
        attempted = succeeded = failed = 0
        for row in rows:
            attempted += 1
            try:
                self.scan_game(int(row["bgg_id"]))
                succeeded += 1
            except Exception:
                failed += 1
        return {"attempted": attempted, "succeeded": succeeded, "failed": failed}
