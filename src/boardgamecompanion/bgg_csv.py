from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from boardgamecompanion.copies import ensure_physical_copies_for_collection_entry
from boardgamecompanion.database import Database

REQUIRED_COLUMNS = {"objectid", "objectname"}


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _to_int(value: str | None) -> int | None:
    value = _none_if_blank(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    value = _none_if_blank(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_bool_int(value: str | None) -> int:
    return 1 if (_none_if_blank(value) or "").lower() in {"1", "true", "yes", "y"} else 0


def _canonical_json(row: dict[str, str]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ImportResult:
    source_filename: str
    sha256: str
    row_count: int
    created_count: int
    updated_count: int
    unchanged_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BggCsvError(ValueError):
    pass


class BggCsvImporter:
    def __init__(self, database: Database):
        self.database = database

    def import_bytes(self, payload: bytes, source_filename: str) -> ImportResult:
        digest = hashlib.sha256(payload).hexdigest()
        rows = self._parse(payload)
        now = datetime.now(UTC).isoformat()
        created = updated = unchanged = 0

        with self.database.transaction() as connection:
            for row in rows:
                status = self._upsert_row(connection, row, now)
                if status == "created":
                    created += 1
                elif status == "updated":
                    updated += 1
                else:
                    unchanged += 1

            connection.execute(
                """
                INSERT INTO import_runs (
                    source_type, source_filename, sha256, row_count,
                    created_count, updated_count, unchanged_count, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "bgg_csv",
                    source_filename,
                    digest,
                    len(rows),
                    created,
                    updated,
                    unchanged,
                    now,
                ),
            )

        return ImportResult(
            source_filename=source_filename,
            sha256=digest,
            row_count=len(rows),
            created_count=created,
            updated_count=updated,
            unchanged_count=unchanged,
        )

    def import_path(self, path: Path) -> ImportResult:
        return self.import_bytes(path.read_bytes(), path.name)

    def _parse(self, payload: bytes) -> list[dict[str, str]]:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BggCsvError("BGG CSV must be UTF-8 encoded") from exc

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise BggCsvError("CSV has no header row")

        normalized = [name.strip().lower() for name in reader.fieldnames if name]
        missing = REQUIRED_COLUMNS - set(normalized)
        if missing:
            raise BggCsvError(f"Missing required BGG columns: {', '.join(sorted(missing))}")

        rows: list[dict[str, str]] = []
        for source_row in reader:
            row = {
                (key or "").strip().lower(): (value or "").strip()
                for key, value in source_row.items()
                if key
            }
            bgg_id = _to_int(row.get("objectid"))
            title = _none_if_blank(row.get("objectname"))
            if bgg_id is None or title is None:
                continue
            rows.append(row)

        if not rows:
            raise BggCsvError("CSV contains no valid BGG collection rows")
        return rows

    def _upsert_row(self, connection, row: dict[str, str], now: str) -> str:
        bgg_id = _to_int(row.get("objectid"))
        assert bgg_id is not None

        board_values = {
            "bgg_id": bgg_id,
            "title": _none_if_blank(row.get("objectname")),
            "original_title": _none_if_blank(row.get("originalname")),
            "year_published": _to_int(row.get("yearpublished")),
            "item_type": _none_if_blank(row.get("itemtype")),
            "min_players": _to_int(row.get("minplayers")),
            "max_players": _to_int(row.get("maxplayers")),
            "playing_time": _to_int(row.get("playingtime")),
            "min_play_time": _to_int(row.get("minplaytime")),
            "max_play_time": _to_int(row.get("maxplaytime")),
            "bgg_average": _to_float(row.get("average")),
            "bgg_bayes_average": _to_float(row.get("baverage")),
            "bgg_average_weight": _to_float(row.get("avgweight")),
            "bgg_rank": _to_int(row.get("rank")),
            "bgg_num_owned": _to_int(row.get("numowned")),
            "bgg_best_players": _none_if_blank(row.get("bggbestplayers")),
            "bgg_recommended_players": _none_if_blank(row.get("bggrecplayers")),
            "bgg_recommended_age": _none_if_blank(row.get("bggrecagerange")),
            "bgg_language_dependence": _none_if_blank(row.get("bgglanguagedependence")),
            "source_metadata_json": _canonical_json(row),
        }

        existing_board = connection.execute(
            "SELECT * FROM board_games WHERE bgg_id = ?", (bgg_id,)
        ).fetchone()

        board_changed = existing_board is None or any(
            existing_board[key] != value for key, value in board_values.items()
        )

        if existing_board is None:
            columns = ", ".join(board_values)
            placeholders = ", ".join("?" for _ in board_values)
            connection.execute(
                f"INSERT INTO board_games ({columns}, created_at, updated_at) VALUES ({placeholders}, ?, ?)",
                (*board_values.values(), now, now),
            )
        elif board_changed:
            assignments = ", ".join(f"{column} = ?" for column in board_values)
            connection.execute(
                f"UPDATE board_games SET {assignments}, updated_at = ? WHERE bgg_id = ?",
                (*board_values.values(), now, bgg_id),
            )

        board_game_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id = ?", (bgg_id,)
        ).fetchone()["id"]

        coll_id = _to_int(row.get("collid"))
        collection_values = {
            "coll_id": coll_id,
            "board_game_id": board_game_id,
            "user_rating": _to_float(row.get("rating")),
            "num_plays": _to_int(row.get("numplays")),
            "user_weight": _to_float(row.get("weight")),
            "own": _to_bool_int(row.get("own")),
            "for_trade": _to_bool_int(row.get("fortrade")),
            "want": _to_bool_int(row.get("want")),
            "want_to_buy": _to_bool_int(row.get("wanttobuy")),
            "want_to_play": _to_bool_int(row.get("wanttoplay")),
            "previously_owned": _to_bool_int(row.get("prevowned")),
            "preordered": _to_bool_int(row.get("preordered")),
            "wishlist": _to_bool_int(row.get("wishlist")),
            "wishlist_priority": _to_int(row.get("wishlistpriority")),
            "wishlist_comment": _none_if_blank(row.get("wishlistcomment")),
            "public_comment": _none_if_blank(row.get("comment")),
            "condition_text": _none_if_blank(row.get("conditiontext")),
            "barcode": _none_if_blank(row.get("barcode")),
            "price_paid": _to_float(row.get("pricepaid")),
            "price_currency": _none_if_blank(row.get("pp_currency")),
            "current_value": _to_float(row.get("currvalue")),
            "current_value_currency": _none_if_blank(row.get("cv_currency")),
            "acquisition_date": _none_if_blank(row.get("acquisitiondate")),
            "acquired_from": _none_if_blank(row.get("acquiredfrom")),
            "quantity": _to_int(row.get("quantity")),
            "private_comment": _none_if_blank(row.get("privatecomment")),
            "inventory_location": _none_if_blank(row.get("invlocation")),
            "inventory_date": _none_if_blank(row.get("invdate")),
            "version_publishers": _none_if_blank(row.get("version_publishers")),
            "version_languages": _none_if_blank(row.get("version_languages")),
            "version_year_published": _to_int(row.get("version_yearpublished")),
            "version_nickname": _none_if_blank(row.get("version_nickname")),
            "source_metadata_json": _canonical_json(row),
        }

        if coll_id is not None:
            existing_entry = connection.execute(
                "SELECT * FROM collection_entries WHERE coll_id = ?", (coll_id,)
            ).fetchone()
        else:
            existing_entry = connection.execute(
                "SELECT * FROM collection_entries WHERE board_game_id = ? AND coll_id IS NULL",
                (board_game_id,),
            ).fetchone()

        collection_changed = existing_entry is None or any(
            existing_entry[key] != value for key, value in collection_values.items()
        )

        if existing_entry is None:
            columns = ", ".join(collection_values)
            placeholders = ", ".join("?" for _ in collection_values)
            cursor = connection.execute(
                f"INSERT INTO collection_entries ({columns}, created_at, updated_at) VALUES ({placeholders}, ?, ?)",
                (*collection_values.values(), now, now),
            )
            ensure_physical_copies_for_collection_entry(
                connection,
                int(cursor.lastrowid),
                now,
            )
            return "created"

        if board_changed or collection_changed:
            assignments = ", ".join(f"{column} = ?" for column in collection_values)
            connection.execute(
                f"UPDATE collection_entries SET {assignments}, updated_at = ? WHERE id = ?",
                (*collection_values.values(), now, existing_entry["id"]),
            )
            ensure_physical_copies_for_collection_entry(
                connection,
                int(existing_entry["id"]),
                now,
            )
            return "updated"

        ensure_physical_copies_for_collection_entry(
            connection,
            int(existing_entry["id"]),
            now,
        )
        return "unchanged"
