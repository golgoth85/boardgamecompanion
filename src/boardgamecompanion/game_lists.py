from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database


class GameListError(ValueError):
    pass


class GameListNotFound(GameListError):
    pass


ALLOWED_SMART_FILTERS = {
    "query", "item_type", "owned", "supports_players", "ideal_players",
    "recommended_players", "player_age", "weight", "max_minutes", "min_rating", "category",
    "mechanic", "completed", "played", "personal_rating_min",
    "personal_rating_max", "sort",
}


def _normalize_filters(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    unknown = set(raw) - ALLOWED_SMART_FILTERS
    if unknown:
        raise GameListError(
            "unsupported smart-list filters: " + ", ".join(sorted(unknown))
        )
    return {key: item for key, item in raw.items() if item not in ("", None)}


class GameListStore:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _row(row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "kind": row["kind"],
            "filters": json.loads(row["filters_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM saved_game_lists ORDER BY name COLLATE NOCASE,id"
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, list_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM saved_game_lists WHERE id=?",
                (str(list_id),),
            ).fetchone()
        if row is None:
            raise GameListNotFound("Game list not found")
        return self._row(row)

    def create(
        self,
        *,
        name: str,
        kind: str,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = str(name).strip()
        kind = str(kind).strip().casefold()
        if not name or len(name) > 200:
            raise GameListError("name is required")
        if kind not in {"smart", "manual"}:
            raise GameListError("kind must be smart or manual")
        normalized = _normalize_filters(filters) if kind == "smart" else {}
        now = datetime.now(UTC).isoformat()
        list_id = str(uuid4())
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO saved_game_lists(
                    id,name,kind,filters_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    list_id,
                    name,
                    kind,
                    json.dumps(normalized, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
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
        if not next_name or len(next_name) > 200:
            raise GameListError("name is required")
        next_filters = current["filters"]
        if filters is not None:
            if current["kind"] != "smart":
                raise GameListError("manual lists do not accept filters")
            next_filters = _normalize_filters(filters)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE saved_game_lists
                SET name=?,filters_json=?,updated_at=?
                WHERE id=?
                """,
                (
                    next_name,
                    json.dumps(next_filters, ensure_ascii=False, sort_keys=True),
                    datetime.now(UTC).isoformat(),
                    str(list_id),
                ),
            )
        return self.get(list_id)

    def delete(self, list_id: str) -> None:
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "DELETE FROM saved_game_lists WHERE id=?",
                (str(list_id),),
            )
            if cursor.rowcount != 1:
                raise GameListNotFound("Game list not found")

    def set_manual_item(self, list_id: str, bgg_id: int, *, present: bool) -> None:
        current = self.get(list_id)
        if current["kind"] != "manual":
            raise GameListError("smart lists cannot be edited item by item")
        with self.database.transaction(immediate=True) as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id=?",
                (int(bgg_id),),
            ).fetchone()
            if game is None:
                raise GameListError("Board game not found")
            if present:
                connection.execute(
                    """
                    INSERT INTO saved_game_list_items(list_id,board_game_id,added_at)
                    VALUES(?,?,?)
                    ON CONFLICT(list_id,board_game_id) DO NOTHING
                    """,
                    (
                        str(list_id),
                        int(game["id"]),
                        datetime.now(UTC).isoformat(),
                    ),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM saved_game_list_items
                    WHERE list_id=? AND board_game_id=?
                    """,
                    (str(list_id), int(game["id"])),
                )

    def resolve(
        self,
        list_id: str,
        *,
        limit: int = 250,
        offset: int = 0,
    ) -> dict[str, Any]:
        current = self.get(list_id)
        limit = max(1, min(int(limit), 5000))
        offset = max(0, int(offset))
        catalog = Catalog(self.database)
        if current["kind"] == "smart":
            kwargs = dict(current["filters"])
            kwargs["limit"] = limit
            kwargs["offset"] = offset
            result = catalog.list_games(**kwargs)
            return {"list": current, **result}

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id
                FROM saved_game_list_items i
                JOIN board_games g ON g.id=i.board_game_id
                WHERE i.list_id=?
                ORDER BY i.added_at DESC,g.title COLLATE NOCASE
                """,
                (str(list_id),),
            ).fetchall()
        identifiers = [int(row["bgg_id"]) for row in rows]
        total = len(identifiers)
        items = [
            item
            for bgg_id in identifiers[offset:offset + limit]
            if (item := catalog.get_game(bgg_id)) is not None
        ]
        return {
            "list": current,
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "sort": "manual",
        }
