from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from boardgamecompanion.database import Database


class NotificationError(ValueError):
    pass


class NotificationNotFound(NotificationError):
    pass


class NotificationStore:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _row(row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "category": row["category"],
            "dedupe_key": row["dedupe_key"],
            "title": row["title"],
            "body": row["body"],
            "target_url": row["target_url"],
            "related_bgg_id": row["related_bgg_id"],
            "read": row["read_at"] is not None,
            "read_at": row["read_at"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }

    def list(self, *, unread_only: bool = False, limit: int = 100) -> dict[str, Any]:
        where = "WHERE read_at IS NULL" if unread_only else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM notifications
                {where}
                ORDER BY created_at DESC,id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 250)),),
            ).fetchall()
            unread = connection.execute(
                "SELECT COUNT(*) AS count FROM notifications WHERE read_at IS NULL"
            ).fetchone()["count"]
        return {
            "items": [self._row(row) for row in rows],
            "unread_count": int(unread or 0),
        }

    def create_once(
        self,
        *,
        category: str,
        dedupe_key: str,
        title: str,
        body: str,
        target_url: str,
        related_bgg_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        category = str(category).strip()
        if category not in {"expansion", "crowdfunding"}:
            raise NotificationError("unsupported notification category")
        if not str(dedupe_key).strip():
            raise NotificationError("dedupe_key is required")
        now = datetime.now(UTC).isoformat()
        notification_id = str(uuid4())
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO notifications(
                    id,category,dedupe_key,title,body,target_url,related_bgg_id,
                    read_at,metadata_json,created_at
                ) VALUES(?,?,?,?,?,?,?,NULL,?,?)
                ON CONFLICT(dedupe_key) DO NOTHING
                """,
                (
                    notification_id,
                    category,
                    str(dedupe_key),
                    str(title).strip()[:500],
                    str(body).strip()[:2000],
                    str(target_url).strip()[:2000],
                    int(related_bgg_id) if related_bgg_id is not None else None,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM notifications WHERE dedupe_key=?",
                (str(dedupe_key),),
            ).fetchone()
        assert row is not None
        return self._row(row)

    def mark_read(self, notification_id: str, *, read: bool = True) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "UPDATE notifications SET read_at=? WHERE id=?",
                (
                    datetime.now(UTC).isoformat() if read else None,
                    str(notification_id),
                ),
            )
            if cursor.rowcount != 1:
                raise NotificationNotFound("Notification not found")
            row = connection.execute(
                "SELECT * FROM notifications WHERE id=?",
                (str(notification_id),),
            ).fetchone()
        assert row is not None
        return self._row(row)
