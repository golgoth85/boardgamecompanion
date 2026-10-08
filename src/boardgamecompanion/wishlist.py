from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from boardgamecompanion.database import Database


class WishlistError(ValueError):
    pass


class WishlistNotFound(WishlistError):
    pass


def _optional_http_url(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if any(ord(char) < 32 or char.isspace() for char in text):
        raise WishlistError(f"{field} must be an HTTP(S) URL")
    try:
        parsed = urlsplit(text)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise WishlistError(f"{field} must be a valid HTTP(S) URL") from exc
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise WishlistError(f"{field} must be an HTTP(S) URL without credentials")
    return text


class WishlistStore:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _row(row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "source_kind": row["source_kind"],
            "source_key": row["source_key"],
            "bgg_id": row["bgg_id"],
            "title": row["title"],
            "year_published": row["year_published"],
            "cover_url": row["cover_url"],
            "target_url": row["target_url"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM personal_wishlist
                ORDER BY updated_at DESC, title COLLATE NOCASE
                """
            ).fetchall()
        return [self._row(row) for row in rows]

    def upsert(
        self,
        *,
        source_kind: str,
        source_key: str,
        title: str,
        bgg_id: int | None = None,
        year_published: int | None = None,
        cover_url: str | None = None,
        target_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_kind = str(source_kind).strip().casefold()
        if source_kind not in {"bgg", "crowdfunding"}:
            raise WishlistError("source_kind must be bgg or crowdfunding")
        source_key = str(source_key).strip()
        title = str(title).strip()
        if not source_key or len(source_key) > 500:
            raise WishlistError("source_key is required")
        if not title or len(title) > 500:
            raise WishlistError("title is required")
        if bgg_id is not None and int(bgg_id) <= 0:
            raise WishlistError("bgg_id must be positive")
        if year_published is not None and not 1000 <= int(year_published) <= 3000:
            raise WishlistError("year_published is invalid")
        cover_url = _optional_http_url(cover_url, field="cover_url")
        target_url = _optional_http_url(target_url, field="target_url")
        now = datetime.now(UTC).isoformat()
        item_id = str(uuid4())
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO personal_wishlist(
                    id,source_kind,source_key,bgg_id,title,year_published,
                    cover_url,target_url,metadata_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_kind,source_key) DO UPDATE SET
                    bgg_id=excluded.bgg_id,
                    title=excluded.title,
                    year_published=excluded.year_published,
                    cover_url=excluded.cover_url,
                    target_url=excluded.target_url,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    item_id,
                    source_kind,
                    source_key,
                    int(bgg_id) if bgg_id is not None else None,
                    title,
                    int(year_published) if year_published is not None else None,
                    cover_url,
                    target_url,
                    metadata_json,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM personal_wishlist WHERE source_kind=? AND source_key=?",
                (source_kind, source_key),
            ).fetchone()
        assert row is not None
        return self._row(row)

    def delete(self, item_id: str) -> None:
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "DELETE FROM personal_wishlist WHERE id=?",
                (str(item_id),),
            )
            if cursor.rowcount != 1:
                raise WishlistNotFound("Wishlist item not found")
