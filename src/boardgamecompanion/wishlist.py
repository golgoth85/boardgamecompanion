from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from boardgamecompanion.database import Database


class WishlistError(ValueError):
    pass


class WishlistService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _clean_text(value: Any, limit: int) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return text[:limit]

    def upsert(
        self,
        *,
        source_type: str,
        source_key: str | None,
        title: str,
        bgg_id: int | None = None,
        year_published: int | None = None,
        cover_url: str | None = None,
        target_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_type = str(source_type or "").strip().lower()
        if source_type not in {"suggestion", "crowdfunding", "bgg", "manual"}:
            raise WishlistError("Unsupported wishlist source")
        title = str(title or "").strip()
        if not title or len(title) > 500:
            raise WishlistError("Wishlist title is required")
        if bgg_id is not None and int(bgg_id) <= 0:
            raise WishlistError("Invalid BGG ID")
        if bgg_id is not None:
            canonical_key = f"bgg:{int(bgg_id)}"
        else:
            canonical_key = str(source_key or "").strip()
            if not canonical_key:
                raise WishlistError("Wishlist source key is required")
        if len(canonical_key) > 1000:
            raise WishlistError("Wishlist source key is too long")

        now = datetime.now(UTC).isoformat()
        payload = metadata if isinstance(metadata, dict) else {}
        with self.database.transaction(immediate=True) as connection:
            existing = connection.execute(
                "SELECT id FROM wishlist_items WHERE source_key=?",
                (canonical_key,),
            ).fetchone()
            if existing is None:
                item_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO wishlist_items(
                        id,source_type,source_key,bgg_id,title,year_published,
                        cover_url,target_url,metadata_json,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        item_id,
                        source_type,
                        canonical_key,
                        int(bgg_id) if bgg_id is not None else None,
                        title,
                        year_published,
                        self._clean_text(cover_url, 2000),
                        self._clean_text(target_url, 2000),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                        now,
                    ),
                )
            else:
                item_id = existing["id"]
                connection.execute(
                    """
                    UPDATE wishlist_items
                    SET source_type=?,bgg_id=COALESCE(?,bgg_id),title=?,
                        year_published=COALESCE(?,year_published),
                        cover_url=COALESCE(?,cover_url),
                        target_url=COALESCE(?,target_url),
                        metadata_json=?,updated_at=?
                    WHERE id=?
                    """,
                    (
                        source_type,
                        int(bgg_id) if bgg_id is not None else None,
                        title,
                        year_published,
                        self._clean_text(cover_url, 2000),
                        self._clean_text(target_url, 2000),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                        item_id,
                    ),
                )
        return self.get(item_id)

    def get(self, item_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT w.*,COALESCE(c.own,0) AS owned
                FROM wishlist_items w
                LEFT JOIN board_games g ON g.bgg_id=w.bgg_id
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                WHERE w.id=?
                ORDER BY c.id
                LIMIT 1
                """,
                (item_id,),
            ).fetchone()
        if row is None:
            raise WishlistError("Wishlist item not found")
        return self._row(row)

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT w.*,MAX(COALESCE(c.own,0)) AS owned
                FROM wishlist_items w
                LEFT JOIN board_games g ON g.bgg_id=w.bgg_id
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                GROUP BY w.id
                ORDER BY w.created_at DESC,w.title COLLATE NOCASE
                """
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> dict[str, Any]:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        bgg_id = row["bgg_id"]
        return {
            "id": row["id"],
            "source_type": row["source_type"],
            "source_key": row["source_key"],
            "bgg_id": bgg_id,
            "title": row["title"],
            "year_published": row["year_published"],
            "cover_url": row["cover_url"],
            "target_url": row["target_url"],
            "metadata": metadata if isinstance(metadata, dict) else {},
            "owned": bool(row["owned"]),
            "local_url": f"/games/{int(bgg_id)}" if bgg_id is not None else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def remove(self, item_id: str) -> None:
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute("DELETE FROM wishlist_items WHERE id=?", (item_id,))
            if cursor.rowcount == 0:
                raise WishlistError("Wishlist item not found")

    def source_keys(self) -> set[str]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT source_key FROM wishlist_items").fetchall()
        return {str(row["source_key"]) for row in rows}
