from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.gameplay_summary import GameplaySummaryService


def _seed_game(database: Database, *, description: str) -> int:
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
            INSERT INTO collection_entries
                (board_game_id,own,created_at,updated_at)
            VALUES (?,1,?,?)
            """,
            (board_game_id, now, now),
        )
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


def test_gameplay_summary_is_generated_once_and_cached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    _seed_game(
        database,
        description=(
            "Players draft cards, place them into a shared market and build combinations. "
            "They score points from completed sets, and the game ends when the deck is exhausted."
        ),
    )
    service = GameplaySummaryService(database)
    fake_rag = SimpleNamespace(generation_provider="gemini")
    monkeypatch.setattr(
        "boardgamecompanion.gameplay_summary.resolve_rag_settings",
        lambda _database: fake_rag,
    )

    calls = 0

    def generate(_prompt: str, _rag):
        nonlocal calls
        calls += 1
        return (
            {
                "summaries": [
                    {
                        "bgg_id": 123456,
                        "summary": (
                            "I giocatori draftano carte, le combinano in set e costruiscono "
                            "progressivamente il proprio motore per ottenere punti prima "
                            "dell'esaurimento del mazzo."
                        ),
                    }
                ]
            },
            "gemini",
            "test-model",
        )

    monkeypatch.setattr(service, "_generate_gemini", generate)

    first = service.ensure_many([123456])
    second = service.ensure_many([123456])

    assert calls == 1
    assert first["generated"] == 1
    assert first["items"][0]["cached"] is False
    assert second["generated"] == 0
    assert second["cached"] == 1
    assert second["items"][0]["summary"].startswith("I giocatori draftano carte")


def test_gameplay_summary_is_invalidated_when_source_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    board_game_id = _seed_game(
        database,
        description=(
            "Players move workers between locations and collect resources to complete projects."
        ),
    )
    service = GameplaySummaryService(database)
    fake_rag = SimpleNamespace(generation_provider="gemini")
    monkeypatch.setattr(
        "boardgamecompanion.gameplay_summary.resolve_rag_settings",
        lambda _database: fake_rag,
    )

    summaries = iter(
        [
            "I giocatori spostano lavoratori tra diverse azioni, raccolgono risorse e completano progetti per ottenere punti e sviluppare progressivamente la propria strategia.",
            "I giocatori selezionano carte azione, controllano aree e convertono risorse in obiettivi, cercando di costruire la combinazione più efficiente prima della fine della partita.",
        ]
    )

    def generate(_prompt: str, _rag):
        return (
            {"summaries": [{"bgg_id": 123456, "summary": next(summaries)}]},
            "gemini",
            "test-model",
        )

    monkeypatch.setattr(service, "_generate_gemini", generate)

    first = service.ensure_many([123456])
    with database.transaction() as connection:
        connection.execute(
            "UPDATE board_game_enrichments SET description=? WHERE board_game_id=?",
            (
                "Players select action cards, control areas and convert resources into objectives.",
                board_game_id,
            ),
        )
    second = service.ensure_many([123456])

    assert first["items"][0]["summary"] != second["items"][0]["summary"]
    assert second["generated"] == 1
