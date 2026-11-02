from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from boardgamecompanion.bgg_metadata import BggApiClient, BggMetadataError
from boardgamecompanion.database import Database
from boardgamecompanion.title_search import alternate_titles, normalize_title_text

LOGGER = logging.getLogger(__name__)

RECHECK_DAYS = 180
RETRY_DAYS = 1
OVERSIZE_RETRY_DAYS = 30
# Edition names such as "Italian edition" describe the release, they are not a title.
_GENERIC_WORDS = frozenset(
    "italian italiano italiana edition edizione version versione first second third "
    "prima seconda terza reprint ristampa printing stampa 1st 2nd 3rd new nuova "
    "revised revisionata".split()
)


def choose_italian_title(versions: list[dict[str, Any]], known_titles: list[str] = ()) -> str | None:
    """The localized name of the Italian edition(s), or ``None`` when BGG lists none.

    Several Italian editions usually share one title; the most common wins, with ties
    broken in favour of a name BGG also lists as an alternate title of the game.
    """
    known = {normalize_title_text(title) for title in known_titles}
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    for version in versions:
        if "Italian" not in (version.get("languages") or []):
            continue
        name = " ".join(str(version.get("name") or "").split())
        key = normalize_title_text(name)
        words = key.split()
        if not key or all(word in _GENERIC_WORDS for word in words):
            continue
        counts[key] += 1
        names.setdefault(key, name)
    if not counts:
        return None
    best = max(counts, key=lambda key: (counts[key], key in known))
    return names[best]


class ItalianTitleService:
    """Collects the Italian edition title of each game, a few games per run."""

    def __init__(self, database: Database, client: BggApiClient | None) -> None:
        self.database = database
        self.client = client

    def due_ids(self, *, limit: int) -> list[int]:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id
                FROM board_games g
                JOIN board_game_enrichments e ON e.board_game_id = g.id
                WHERE COALESCE(json_extract(e.metadata_json, '$.italian_title_next_check_at'), '') <= ?
                ORDER BY EXISTS(
                             SELECT 1 FROM collection_entries c
                             WHERE c.board_game_id = g.id AND c.own = 1
                         ) DESC,
                         COALESCE(json_extract(e.metadata_json, '$.italian_title_next_check_at'), '') ASC,
                         g.bgg_id
                LIMIT ?
                """,
                (now, max(1, int(limit))),
            ).fetchall()
        return [int(row["bgg_id"]) for row in rows]

    def scan_due(self, *, limit: int = 5) -> dict[str, int]:
        summary = {"checked": 0, "found": 0, "failed": 0}
        if self.client is None:
            return summary
        for bgg_id in self.due_ids(limit=limit):
            try:
                title = self.check(bgg_id)
            except BggMetadataError as exc:
                LOGGER.warning("Italian title scan failed for BGG #%s: %s", bgg_id, exc)
                oversize = "byte limit" in str(exc)
                self._store(bgg_id, None, OVERSIZE_RETRY_DAYS if oversize else RETRY_DAYS, keep=True)
                summary["failed"] += 1
                continue
            summary["checked"] += 1
            summary["found"] += title is not None
        return summary

    def check(self, bgg_id: int) -> str | None:
        assert self.client is not None
        versions = self.client.versions(bgg_id)
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT e.metadata_json FROM board_game_enrichments e
                   JOIN board_games g ON g.id = e.board_game_id WHERE g.bgg_id = ?""",
                (bgg_id,),
            ).fetchone()
        known = alternate_titles(row["metadata_json"]) if row else []
        title = choose_italian_title(versions, known)
        self._store(bgg_id, title, RECHECK_DAYS)
        return title

    def _store(self, bgg_id: int, title: str | None, days: int, *, keep: bool = False) -> None:
        next_check = (datetime.now(UTC) + timedelta(days=days)).isoformat()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """SELECT e.board_game_id, e.metadata_json FROM board_game_enrichments e
                   JOIN board_games g ON g.id = e.board_game_id WHERE g.bgg_id = ?""",
                (bgg_id,),
            ).fetchone()
            if row is None:
                return
            metadata = json.loads(row["metadata_json"] or "{}")
            metadata["italian_title_next_check_at"] = next_check
            if not keep:
                if title:
                    metadata["italian_title"] = title
                else:
                    metadata.pop("italian_title", None)
            connection.execute(
                "UPDATE board_game_enrichments SET metadata_json = ? WHERE board_game_id = ?",
                (json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":")), row["board_game_id"]),
            )
