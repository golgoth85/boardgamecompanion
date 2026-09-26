from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from boardgamecompanion.bgg_metadata import BggMetadataStore
from boardgamecompanion.database import Database
from boardgamecompanion.rulebook_review import RulebookReviewQueue
from boardgamecompanion.rulebooks import RulebookProvider, RulebookQuery, RulebookResolver


class RulebookDiscoveryError(RuntimeError):
    pass


class RulebookDiscoveryNotFound(RulebookDiscoveryError):
    pass


class RulebookDiscoveryBusy(RulebookDiscoveryError):
    pass


def _now(value: datetime | None = None) -> datetime:
    return (value or datetime.now(UTC)).astimezone(UTC)


def _publishers(value: str | None) -> list[str]:
    if not value:
        return []
    for separator in (";", "|"):
        value = value.replace(separator, ",")
    return [part.strip() for part in value.split(",") if part.strip()]


class RulebookDiscoveryService:
    def __init__(
        self,
        database: Database,
        providers: tuple[RulebookProvider, ...],
        *,
        metadata_store: BggMetadataStore | None = None,
        refresh_seconds: int = 14 * 24 * 60 * 60,
        empty_refresh_seconds: int = 3 * 24 * 60 * 60,
        retry_base_seconds: int = 6 * 60 * 60,
        retry_max_seconds: int = 3 * 24 * 60 * 60,
        lease_seconds: int = 15 * 60,
    ) -> None:
        self.database = database
        self.providers = tuple(providers)
        self.resolver = RulebookResolver(self.providers)
        self.metadata_store = metadata_store
        self.refresh_seconds = int(refresh_seconds)
        self.empty_refresh_seconds = int(empty_refresh_seconds)
        self.retry_base_seconds = int(retry_base_seconds)
        self.retry_max_seconds = int(retry_max_seconds)
        self.lease_seconds = int(lease_seconds)

    def synchronize_catalog(self, *, now: datetime | None = None) -> int:
        current = _now(now).isoformat()
        with self.database.transaction(immediate=True) as connection:
            result = connection.execute(
                """INSERT INTO rulebook_discovery_games
                   (board_game_id,next_attempt_at,created_at,updated_at)
                   SELECT g.id,?,?,? FROM board_games g
                   LEFT JOIN rulebook_discovery_games d ON d.board_game_id=g.id
                   WHERE d.board_game_id IS NULL""",
                (current, current, current),
            )
        return int(result.rowcount)

    def _query(self, bgg_id: int) -> RulebookQuery:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT g.*, GROUP_CONCAT(c.version_publishers, ';') AS version_publishers
                   FROM board_games g LEFT JOIN collection_entries c ON c.board_game_id=g.id
                   WHERE g.bgg_id=? GROUP BY g.id""", (int(bgg_id),)
            ).fetchone()
        if row is None:
            raise RulebookDiscoveryNotFound(f"Board game BGG #{bgg_id} not found")
        metadata = self.metadata_store.get(bgg_id) if self.metadata_store else None
        publishers = _publishers(row["version_publishers"])
        if metadata:
            publishers.extend(str(value) for value in metadata["publishers"])
        return RulebookQuery(
            bgg_id=int(row["bgg_id"]),
            title=str(row["title"]),
            original_title=(metadata or {}).get("original_title") or row["original_title"],
            year=(metadata or {}).get("year_published") or row["year_published"],
            item_type=(metadata or {}).get("metadata", {}).get("item_type") or row["item_type"],
            publishers=tuple(dict.fromkeys(publishers)),
            verified_publishers=(
                tuple(str(value) for value in metadata["publishers"])
                if metadata and metadata.get("fetched_at")
                and metadata.get("metadata", {}).get("bgg_id") == int(bgg_id)
                else ()
            ),
            verified_titles=(
                tuple(
                    dict.fromkeys(
                        str(value)
                        for value in (
                            metadata.get("title"),
                            metadata.get("original_title"),
                        )
                        if value
                    )
                )
                if metadata and metadata.get("fetched_at")
                and metadata.get("metadata", {}).get("bgg_id") == int(bgg_id)
                else ()
            ),
            bgg_identity_verified=bool(
                metadata
                and metadata.get("fetched_at")
                and metadata.get("metadata", {}).get("bgg_id") == int(bgg_id)
            ),
        )

    def _claim(self, bgg_id: int, *, force: bool, now: datetime) -> tuple[int, str, int]:
        owner = str(uuid4())
        current = now.isoformat()
        lease_until = (now + timedelta(seconds=self.lease_seconds)).isoformat()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """SELECT d.*,g.id AS game_id FROM board_games g
                   JOIN rulebook_discovery_games d ON d.board_game_id=g.id
                   WHERE g.bgg_id=?""", (int(bgg_id),)
            ).fetchone()
            if row is None:
                raise RulebookDiscoveryNotFound(f"Discovery state for BGG #{bgg_id} not found")
            if row["lease_until"] and row["lease_until"] > current:
                raise RulebookDiscoveryBusy(f"Discovery for BGG #{bgg_id} is already running")
            if not force and (not row["enabled"] or row["next_attempt_at"] > current):
                raise RulebookDiscoveryBusy(f"Discovery for BGG #{bgg_id} is not due")
            generation = int(row["lease_generation"]) + 1
            connection.execute(
                """UPDATE rulebook_discovery_games SET status='running',last_started_at=?,
                   attempt_count=attempt_count+1,lease_owner=?,lease_until=?,lease_generation=?,updated_at=?
                   WHERE board_game_id=?""",
                (current, owner, lease_until, generation, current, row["game_id"]),
            )
        return int(row["game_id"]), owner, generation

    def run_game(self, bgg_id: int, *, force: bool = True, now: datetime | None = None) -> dict[str, Any]:
        current = _now(now)
        game_id, owner, generation = self._claim(bgg_id, force=force, now=current)
        if self.metadata_store is not None and self.metadata_store.client is not None:
            try:
                self.metadata_store.refresh(bgg_id, force=False, now=current)
            except Exception:
                # BGG metadata is matching evidence, never a hard dependency for
                # CSV-backed catalog discovery.
                pass
        query = self._query(bgg_id)
        resolution = self.resolver.resolve(query, preferred_languages=("it", "en"))
        queue = RulebookReviewQueue(self.database)
        created = 0
        for resolved in resolution.candidates:
            _, was_created = queue.submit(bgg_id=int(bgg_id), candidate=resolved.candidate)
            created += int(was_created)
        finished = _now()
        failures = len(resolution.failures)
        candidates = len(resolution.candidates)
        if failures == len(self.providers) and not candidates:
            status = "failed"
        elif failures:
            status = "partial"
        else:
            status = "succeeded"
        if status == "failed":
            with self.database.connect() as connection:
                prior = connection.execute("SELECT consecutive_failures FROM rulebook_discovery_games WHERE board_game_id=?", (game_id,)).fetchone()
            failure_count = int(prior["consecutive_failures"]) + 1
            delay = min(self.retry_base_seconds * (2 ** (failure_count - 1)), self.retry_max_seconds)
        else:
            failure_count = 0
            delay = self.refresh_seconds if candidates else self.empty_refresh_seconds
        next_attempt = finished + timedelta(seconds=delay)
        failure_map = {failure.provider: failure for failure in resolution.failures}
        with self.database.transaction(immediate=True) as connection:
            fenced = connection.execute(
                "SELECT lease_owner,lease_generation FROM rulebook_discovery_games WHERE board_game_id=?", (game_id,)
            ).fetchone()
            if fenced is None or fenced["lease_owner"] != owner or int(fenced["lease_generation"]) != generation:
                raise RulebookDiscoveryBusy("Discovery lease changed before completion")
            for provider in self.providers:
                name = str(provider.name)
                failure = failure_map.get(name)
                count = sum(1 for item in resolution.candidates if item.candidate.provider == name)
                connection.execute(
                    """INSERT INTO rulebook_discovery_provider_runs
                       (id,board_game_id,lease_generation,provider,started_at,finished_at,outcome,
                        candidate_count,error_type,error_message)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid4()), game_id, generation, name, current.isoformat(), finished.isoformat(),
                     "failed" if failure else "succeeded", count,
                     failure.error_type if failure else None, failure.message[:1000] if failure else None),
                )
            connection.execute(
                """UPDATE rulebook_discovery_games SET status=?,next_attempt_at=?,last_finished_at=?,
                   consecutive_failures=?,providers_queried=?,candidates_found=?,review_items_created=?,
                   provider_failures=?,last_error=?,lease_owner=NULL,lease_until=NULL,updated_at=?
                   WHERE board_game_id=? AND lease_owner=? AND lease_generation=?""",
                (status, next_attempt.isoformat(), finished.isoformat(), failure_count, len(self.providers),
                 candidates, created, failures,
                 json.dumps([{"provider": f.provider, "type": f.error_type, "message": f.message[:500]} for f in resolution.failures]) if failures else None,
                 finished.isoformat(), game_id, owner, generation),
            )
        return {"bgg_id": int(bgg_id), "status": status, "providers_queried": len(self.providers),
                "candidates_found": candidates, "review_items_created": created,
                "provider_failures": failures, "next_attempt_at": next_attempt.isoformat()}

    def run_due(self, *, limit: int = 5) -> dict[str, Any]:
        self.synchronize_catalog()
        current = _now().isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT g.bgg_id FROM rulebook_discovery_games d JOIN board_games g ON g.id=d.board_game_id
                   WHERE d.enabled=1 AND d.next_attempt_at<=? AND (d.lease_until IS NULL OR d.lease_until<=?)
                   ORDER BY EXISTS(
                       SELECT 1 FROM game_documents doc
                       WHERE doc.board_game_id=d.board_game_id
                         AND doc.document_type='rulebook'
                   ), d.next_attempt_at,g.bgg_id LIMIT ?""", (current, current, max(1, min(int(limit), 100)))
            ).fetchall()
        items = []
        for row in rows:
            try:
                items.append(self.run_game(int(row["bgg_id"]), force=False))
            except RulebookDiscoveryBusy:
                continue
        return {"attempted": len(items), "items": items}

    def list_status(self, *, bgg_id: int | None = None, limit: int = 250) -> dict[str, Any]:
        self.synchronize_catalog()
        where = "WHERE g.bgg_id=?" if bgg_id is not None else ""
        params: tuple[Any, ...] = (int(bgg_id),) if bgg_id is not None else ()
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""SELECT d.*,g.bgg_id,g.title FROM rulebook_discovery_games d
                    JOIN board_games g ON g.id=d.board_game_id {where}
                    ORDER BY d.next_attempt_at,g.title LIMIT ?""", (*params, max(1, min(int(limit), 500)))
            ).fetchall()
            items: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                provider_rows = connection.execute(
                    """SELECT provider,outcome,candidate_count,error_type,error_message,finished_at
                       FROM rulebook_discovery_provider_runs
                       WHERE board_game_id=? AND lease_generation=? ORDER BY provider""",
                    (row["board_game_id"], row["lease_generation"]),
                ).fetchall()
                item["providers"] = [dict(provider_row) for provider_row in provider_rows]
                items.append(item)
        return {"count": len(items), "items": items}
