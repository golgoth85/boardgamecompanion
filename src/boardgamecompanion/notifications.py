from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from boardgamecompanion.database import Database


_WORD_RE = re.compile(r"[a-z0-9]+", re.I)
_STOP = {
    "the","game","board","edition","deluxe","kickstarter","gamefound","campaign",
    "expansion","new","reprint","second","2nd","anniversary","ultimate",
}


def _normalized(value: str) -> str:
    return " ".join(_WORD_RE.findall(str(value or "").casefold()))


def _tokens(value: str) -> set[str]:
    return {word for word in _WORD_RE.findall(str(value or "").casefold()) if len(word) >= 4 and word not in _STOP}


def _title_matches(reference: str, candidate: str) -> bool:
    ref = _normalized(reference)
    cand = _normalized(candidate)
    if not ref or not cand:
        return False
    if len(ref) >= 5 and ref in cand:
        return True
    left = _tokens(reference)
    right = _tokens(candidate)
    if len(left) < 2:
        return False
    overlap = len(left & right)
    return overlap >= 2 and overlap / max(1, len(left)) >= 0.7


class NotificationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_once(
        self,
        *,
        dedupe_key: str,
        category: str,
        title: str,
        body: str,
        target_url: str | None,
        source: dict[str, Any] | None = None,
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                INSERT INTO app_notifications(
                    id,dedupe_key,category,title,body,target_url,source_json,
                    read_at,created_at
                ) VALUES(?,?,?,?,?,?,?,NULL,?)
                ON CONFLICT(dedupe_key) DO NOTHING
                """,
                (
                    str(uuid4()),
                    str(dedupe_key)[:1000],
                    str(category)[:64],
                    str(title)[:500],
                    str(body)[:2000],
                    str(target_url)[:2000] if target_url else None,
                    json.dumps(source or {}, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
        return cursor.rowcount > 0

    def list(self, *, unread_only: bool = False, limit: int = 100) -> dict[str, Any]:
        where = "WHERE read_at IS NULL" if unread_only else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM app_notifications
                {where}
                ORDER BY created_at DESC,id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 250)),),
            ).fetchall()
            unread = connection.execute(
                "SELECT COUNT(*) AS count FROM app_notifications WHERE read_at IS NULL"
            ).fetchone()["count"]
        items = []
        for row in rows:
            try:
                source = json.loads(row["source_json"] or "{}")
            except (TypeError, ValueError):
                source = {}
            items.append(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "title": row["title"],
                    "body": row["body"],
                    "target_url": row["target_url"],
                    "source": source if isinstance(source, dict) else {},
                    "read": bool(row["read_at"]),
                    "read_at": row["read_at"],
                    "created_at": row["created_at"],
                }
            )
        return {"items": items, "unread_count": int(unread or 0)}

    def mark_read(self, notification_id: str, *, read: bool = True) -> dict[str, Any]:
        value = datetime.now(UTC).isoformat() if read else None
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "UPDATE app_notifications SET read_at=? WHERE id=?",
                (value, notification_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("Notification not found")
        return self.list(limit=250)

    def mark_all_read(self) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE app_notifications SET read_at=? WHERE read_at IS NULL",
                (datetime.now(UTC).isoformat(),),
            )
        return self.list(limit=250)

    def sync_crowdfunding(self, campaigns: list[dict[str, Any]]) -> int:
        with self.database.connect() as connection:
            owned = connection.execute(
                """
                SELECT DISTINCT g.bgg_id,g.title
                FROM board_games g
                JOIN collection_entries c ON c.board_game_id=g.id
                WHERE c.own=1 AND COALESCE(g.item_type,'standalone')!='expansion'
                """
            ).fetchall()
            wished = connection.execute(
                "SELECT bgg_id,title,source_key FROM wishlist_items"
            ).fetchall()

        references: list[tuple[str, str]] = [
            (f"bgg:{int(row['bgg_id'])}", str(row["title"])) for row in owned
        ]
        references.extend(
            (str(row["source_key"]), str(row["title"]))
            for row in wished
            if row["title"]
        )
        now = datetime.now(UTC)
        created = 0
        for campaign in campaigns:
            campaign_id = str(campaign.get("id") or "").strip()
            title = str(campaign.get("title") or "").strip()
            if not campaign_id or not title:
                continue
            start_raw = campaign.get("campaign_start")
            if start_raw:
                try:
                    start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=UTC)
                    if start < now - timedelta(days=45):
                        continue
                except ValueError:
                    pass
            matched = next(
                (
                    (key, ref_title)
                    for key, ref_title in references
                    if key != campaign_id and _title_matches(ref_title, title)
                ),
                None,
            )
            if matched is None:
                continue
            key, ref_title = matched
            if self.create_once(
                dedupe_key=f"crowdfunding:{campaign_id}:{key}",
                category="crowdfunding",
                title=f"Nuovo crowdfunding: {title}",
                body=f"Campagna collegata a {ref_title}.",
                target_url=str(campaign.get("project_url") or "") or None,
                source={"campaign_id": campaign_id, "reference_key": key},
            ):
                created += 1
        return created
