from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database


class GameListError(ValueError):
    pass


DYNAMIC_FILTERS = {
    "query",
    "item_type",
    "owned",
    "supports_players",
    "ideal_players",
    "player_age",
    "weight",
    "max_minutes",
    "min_rating",
    "personal_rating_min",
    "category",
    "mechanic",
    "completed",
    "played",
    "trophy",
    "sort",
}


def _clean_filters(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise GameListError("List filters must be an object")
    unknown = set(value) - DYNAMIC_FILTERS
    if unknown:
        raise GameListError("Unsupported list filters: " + ", ".join(sorted(unknown)))
    cleaned: dict[str, Any] = {}
    for key, raw in value.items():
        if raw is None or raw == "":
            continue
        cleaned[key] = raw
    return cleaned


class GameListService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_all(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT l.*,
                       (SELECT COUNT(*) FROM game_list_items i WHERE i.list_id=l.id)
                           AS manual_count
                FROM game_lists l
                ORDER BY l.name COLLATE NOCASE,l.created_at
                """
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, list_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT l.*,
                       (SELECT COUNT(*) FROM game_list_items i WHERE i.list_id=l.id)
                           AS manual_count
                FROM game_lists l WHERE l.id=?
                """,
                (list_id,),
            ).fetchone()
        if row is None:
            raise GameListError("List not found")
        return self._row(row)

    @staticmethod
    def _row(row) -> dict[str, Any]:
        try:
            filters = json.loads(row["filters_json"] or "{}")
        except (TypeError, ValueError):
            filters = {}
        return {
            "id": row["id"],
            "name": row["name"],
            "kind": row["kind"],
            "filters": filters if isinstance(filters, dict) else {},
            "manual_count": int(row["manual_count"] or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create(
        self,
        *,
        name: str,
        kind: str,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = str(name or "").strip()
        if not name or len(name) > 120:
            raise GameListError("List name must contain 1..120 characters")
        kind = str(kind or "").strip().lower()
        if kind not in {"dynamic", "manual"}:
            raise GameListError("List kind must be dynamic or manual")
        clean = _clean_filters(filters) if kind == "dynamic" else {}
        now = datetime.now(UTC).isoformat()
        list_id = str(uuid4())
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO game_lists(id,name,kind,filters_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?)
                """,
                (list_id, name, kind, json.dumps(clean, ensure_ascii=False, sort_keys=True), now, now),
            )
        return self.get(list_id)

    def update(
        self,
        list_id: str,
        *,
        name: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get(list_id)
        next_name = current["name"] if name is None else str(name).strip()
        if not next_name or len(next_name) > 120:
            raise GameListError("List name must contain 1..120 characters")
        if current["kind"] == "manual" and filters is not None:
            raise GameListError("Manual lists do not use dynamic filters")
        next_filters = current["filters"] if filters is None else _clean_filters(filters)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE game_lists SET name=?,filters_json=?,updated_at=? WHERE id=?
                """,
                (
                    next_name,
                    json.dumps(next_filters, ensure_ascii=False, sort_keys=True),
                    datetime.now(UTC).isoformat(),
                    list_id,
                ),
            )
        return self.get(list_id)

    def delete(self, list_id: str) -> None:
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute("DELETE FROM game_lists WHERE id=?", (list_id,))
            if cursor.rowcount == 0:
                raise GameListError("List not found")

    def add_game(self, list_id: str, bgg_id: int) -> dict[str, Any]:
        current = self.get(list_id)
        if current["kind"] != "manual":
            raise GameListError("Only manual lists accept explicit games")
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id=?",
                (int(bgg_id),),
            ).fetchone()
            if game is None:
                raise GameListError("Board game not found")
            position = connection.execute(
                "SELECT COALESCE(MAX(position),0)+1 AS value FROM game_list_items WHERE list_id=?",
                (list_id,),
            ).fetchone()["value"]
            connection.execute(
                """
                INSERT INTO game_list_items(list_id,board_game_id,position,created_at)
                VALUES(?,?,?,?)
                ON CONFLICT(list_id,board_game_id) DO NOTHING
                """,
                (list_id, int(game["id"]), int(position or 1), now),
            )
            connection.execute(
                "UPDATE game_lists SET updated_at=? WHERE id=?",
                (now, list_id),
            )
        return self.evaluate(list_id)

    def remove_game(self, list_id: str, bgg_id: int) -> dict[str, Any]:
        current = self.get(list_id)
        if current["kind"] != "manual":
            raise GameListError("Only manual lists accept explicit games")
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                DELETE FROM game_list_items
                WHERE list_id=? AND board_game_id=(
                    SELECT id FROM board_games WHERE bgg_id=?
                )
                """,
                (list_id, int(bgg_id)),
            )
            connection.execute(
                "UPDATE game_lists SET updated_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), list_id),
            )
        return self.evaluate(list_id)

    def evaluate(self, list_id: str, *, limit: int = 5000) -> dict[str, Any]:
        current = self.get(list_id)
        catalog = Catalog(self.database)
        if current["kind"] == "dynamic":
            filters = dict(current["filters"])
            filters.setdefault("owned", True)
            filters.setdefault("sort", "title")
            payload = catalog.list_games(limit=min(max(1, int(limit)), 5000), offset=0, **filters)
            items = payload["items"]
        else:
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT g.bgg_id
                    FROM game_list_items i
                    JOIN board_games g ON g.id=i.board_game_id
                    WHERE i.list_id=?
                    ORDER BY i.position,g.title COLLATE NOCASE
                    """,
                    (list_id,),
                ).fetchall()
            items = []
            for row in rows[:limit]:
                game = catalog.get_game(int(row["bgg_id"]))
                if game is not None:
                    items.append(game)
        return {
            **current,
            "items": items,
            "count": len(items),
            "evaluated_at": datetime.now(UTC).isoformat(),
        }
