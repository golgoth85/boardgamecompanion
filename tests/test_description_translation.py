from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from boardgamecompanion.database import Database
from boardgamecompanion.description_translation import (
    DescriptionTranslationService,
    _clean_source,
)


def _seed_game(database: Database, *, description: str | None) -> int:
    now = datetime.now(UTC).isoformat()
    with database.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO board_games
                (bgg_id,title,original_title,item_type,created_at,updated_at)
            VALUES (123456,'Synthetic Game','Synthetic Game','standalone',?,?)
            """,
            (now, now),
        )
        board_game_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO board_game_enrichments
                (board_game_id,source,external_id,description,next_refresh_at,
                 created_at,updated_at)
            VALUES (?,'bgg_xml_api2','123456',?,'2099-01-01T00:00:00+00:00',?,?)
            """,
            (board_game_id, description, now, now),
        )
    return board_game_id


def test_cached_translation_is_bound_to_source_hash(tmp_path: Path) -> None:
    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    board_game_id = _seed_game(database, description="A tactical <b>board game</b>.<br>Second line.")
    service = DescriptionTranslationService(database)

    source = _clean_source("A tactical <b>board game</b>.<br>Second line.")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO board_game_description_translations
                (board_game_id,source_sha256,source_language,target_language,
                 translated_text,provider,model,translated_at)
            VALUES (?,?,'en','it','Un gioco da tavolo tattico.\nSeconda riga.',
                    'gemini','test-model','2026-10-03T00:00:00+00:00')
            """,
            (board_game_id, digest),
        )

    cached = service.get_cached(123456)
    assert cached is not None
    assert cached["translated_text"].startswith("Un gioco")

    with database.transaction() as connection:
        connection.execute(
            "UPDATE board_game_enrichments SET description=? WHERE board_game_id=?",
            ("A different description.", board_game_id),
        )

    assert service.get_cached(123456) is None
    assert service.status(123456)["status"] == "pending"


def test_description_status_handles_missing_source(tmp_path: Path) -> None:
    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    _seed_game(database, description=None)

    status = DescriptionTranslationService(database).status(123456)
    assert status == {
        "bgg_id": 123456,
        "source_available": False,
        "status": "missing_source",
        "translation": None,
    }
