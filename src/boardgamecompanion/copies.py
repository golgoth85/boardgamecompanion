from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from boardgamecompanion.database import Database


COPY_MUTABLE_FIELDS = {
    "barcode",
    "language",
    "edition",
    "publishers",
    "version_year_published",
    "acquisition_date",
    "acquired_from",
    "price_paid",
    "price_currency",
    "condition_text",
    "inventory_location",
    "notes",
}


class PhysicalCopyError(ValueError):
    pass


class PhysicalCopyNotFound(PhysicalCopyError):
    pass


class BoardGameNotFound(PhysicalCopyError):
    pass


def normalize_barcode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(char for char in str(value).upper() if char.isalnum())
    return normalized or None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _copy_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "bgg_id": row["bgg_id"],
        "game_title": row["game_title"],
        "source": {
            "kind": row["source_kind"],
            "collection_entry_id": row["source_collection_entry_id"],
            "copy_index": row["source_copy_index"],
        },
        "barcode": row["barcode"],
        "barcode_normalized": row["barcode_normalized"],
        "language": row["language"],
        "edition": row["edition"],
        "publishers": row["publishers"],
        "version_year_published": row["version_year_published"],
        "acquisition_date": row["acquisition_date"],
        "acquired_from": row["acquired_from"],
        "price_paid": row["price_paid"],
        "price_currency": row["price_currency"],
        "condition": row["condition_text"],
        "inventory_location": row["inventory_location"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _source_values(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "barcode": row["barcode"],
        "barcode_normalized": normalize_barcode(row["barcode"]),
        "language": row["version_languages"],
        "edition": row["version_nickname"],
        "publishers": row["version_publishers"],
        "version_year_published": row["version_year_published"],
        "acquisition_date": row["acquisition_date"],
        "acquired_from": row["acquired_from"],
        "price_paid": row["price_paid"],
        "price_currency": row["price_currency"],
        "condition_text": row["condition_text"],
        "inventory_location": row["inventory_location"],
        "notes": row["private_comment"],
    }


def ensure_physical_copies_for_collection_entry(
    connection: sqlite3.Connection,
    collection_entry_id: int,
    now: str | None = None,
) -> int:
    """Create only missing imported copies; never overwrite or delete user edits."""

    row = connection.execute(
        """
        SELECT id, board_game_id, own, quantity, barcode,
               version_languages, version_nickname, version_publishers,
               version_year_published, acquisition_date, acquired_from,
               price_paid, price_currency, condition_text,
               inventory_location, private_comment
        FROM collection_entries
        WHERE id = ?
        """,
        (collection_entry_id,),
    ).fetchone()
    if row is None or not bool(row["own"]):
        return 0

    quantity = row["quantity"]
    expected = int(quantity) if quantity is not None and int(quantity) > 0 else 1
    existing = {
        int(existing_row["source_copy_index"])
        for existing_row in connection.execute(
            """
            SELECT source_copy_index
            FROM physical_copies
            WHERE source_collection_entry_id = ?
              AND source_copy_index IS NOT NULL
            """,
            (collection_entry_id,),
        ).fetchall()
    }

    timestamp = now or datetime.now(UTC).isoformat()
    values = _source_values(row)
    created = 0

    for copy_index in range(1, expected + 1):
        if copy_index in existing:
            continue
        connection.execute(
            """
            INSERT INTO physical_copies (
                id, board_game_id, source_collection_entry_id,
                source_copy_index, source_kind, barcode,
                barcode_normalized, language, edition, publishers,
                version_year_published, acquisition_date, acquired_from,
                price_paid, price_currency, condition_text,
                inventory_location, notes, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, 'bgg_csv', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                str(uuid4()),
                row["board_game_id"],
                collection_entry_id,
                copy_index,
                values["barcode"],
                values["barcode_normalized"],
                values["language"],
                values["edition"],
                values["publishers"],
                values["version_year_published"],
                values["acquisition_date"],
                values["acquired_from"],
                values["price_paid"],
                values["price_currency"],
                values["condition_text"],
                values["inventory_location"],
                values["notes"],
                timestamp,
                timestamp,
            ),
        )
        created += 1

    return created


class PhysicalCopyStore:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _select_sql(where: str) -> str:
        return f"""
            SELECT pc.*, g.bgg_id, g.title AS game_title
            FROM physical_copies pc
            JOIN board_games g ON g.id = pc.board_game_id
            WHERE {where}
        """

    def list_for_game(self, bgg_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                self._select_sql("g.bgg_id = ?") + """
                ORDER BY
                    pc.source_collection_entry_id IS NULL,
                    pc.source_collection_entry_id,
                    pc.source_copy_index,
                    pc.created_at,
                    pc.id
                """,
                (bgg_id,),
            ).fetchall()
        return [_copy_dict(row) for row in rows]

    def get(self, copy_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                self._select_sql("pc.id = ?"),
                (copy_id,),
            ).fetchone()
        return _copy_dict(row) if row else None

    def create(self, bgg_id: int, values: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        copy_id = str(uuid4())

        with self.database.transaction() as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id = ?",
                (bgg_id,),
            ).fetchone()
            if game is None:
                raise BoardGameNotFound(f"Board game BGG #{bgg_id} not found")

            cleaned = self._clean_values(values)
            connection.execute(
                """
                INSERT INTO physical_copies (
                    id, board_game_id, source_kind, barcode,
                    barcode_normalized, language, edition, publishers,
                    version_year_published, acquisition_date, acquired_from,
                    price_paid, price_currency, condition_text,
                    inventory_location, notes, created_at, updated_at
                ) VALUES (
                    ?, ?, 'manual', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    copy_id,
                    game["id"],
                    cleaned.get("barcode"),
                    cleaned.get("barcode_normalized"),
                    cleaned.get("language"),
                    cleaned.get("edition"),
                    cleaned.get("publishers"),
                    cleaned.get("version_year_published"),
                    cleaned.get("acquisition_date"),
                    cleaned.get("acquired_from"),
                    cleaned.get("price_paid"),
                    cleaned.get("price_currency"),
                    cleaned.get("condition_text"),
                    cleaned.get("inventory_location"),
                    cleaned.get("notes"),
                    now,
                    now,
                ),
            )

        created = self.get(copy_id)
        assert created is not None
        return created

    def update(self, copy_id: str, values: dict[str, Any]) -> dict[str, Any]:
        unknown = set(values) - COPY_MUTABLE_FIELDS
        if unknown:
            raise PhysicalCopyError(
                f"Unsupported physical copy fields: {', '.join(sorted(unknown))}"
            )

        cleaned = self._clean_values(values)
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in cleaned.items():
            if key == "barcode_normalized":
                continue
            assignments.append(f"{key} = ?")
            params.append(value)

        if "barcode" in values:
            assignments.append("barcode_normalized = ?")
            params.append(cleaned.get("barcode_normalized"))

        if not assignments:
            current = self.get(copy_id)
            if current is None:
                raise PhysicalCopyNotFound(f"Physical copy {copy_id} not found")
            return current

        assignments.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(copy_id)

        with self.database.transaction() as connection:
            cursor = connection.execute(
                f"""
                UPDATE physical_copies
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                params,
            )
            if cursor.rowcount != 1:
                raise PhysicalCopyNotFound(f"Physical copy {copy_id} not found")

        updated = self.get(copy_id)
        assert updated is not None
        return updated

    def lookup_barcode(self, barcode: str) -> dict[str, Any]:
        normalized = normalize_barcode(barcode)
        if normalized is None:
            raise PhysicalCopyError("Barcode is empty")

        with self.database.connect() as connection:
            rows = connection.execute(
                self._select_sql("pc.barcode_normalized = ?") + """
                ORDER BY g.title COLLATE NOCASE, pc.created_at, pc.id
                """,
                (normalized,),
            ).fetchall()

        matches = [_copy_dict(row) for row in rows]
        return {
            "barcode": _clean_text(barcode),
            "normalized": normalized,
            "count": len(matches),
            "matches": matches,
        }

    @staticmethod
    def _clean_values(values: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in values.items():
            if key not in COPY_MUTABLE_FIELDS:
                continue
            if key in {
                "barcode",
                "language",
                "edition",
                "publishers",
                "acquisition_date",
                "acquired_from",
                "price_currency",
                "condition_text",
                "inventory_location",
                "notes",
            }:
                cleaned[key] = _clean_text(value)
            else:
                cleaned[key] = value

        if "barcode" in values:
            cleaned["barcode_normalized"] = normalize_barcode(cleaned.get("barcode"))
        return cleaned
