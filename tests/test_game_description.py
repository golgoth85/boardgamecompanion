from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.game_description import (
    OPENING_ANGLES,
    GameDescriptionError,
    GameDescriptionService,
    _clean_output,
    _opening_angle,
    _style_problems,
)

GOOD = (
    "Al centro del tavolo si apre un libro pop-up di cartone che fa da mappa. "
    + "Ogni capitolo porta in una zona nuova e cambia gli obiettivi della partita. " * 8
    + "\n\n"
    + "Le regole arrivano poco alla volta da un mazzo di carte già ordinate. " * 6
)


def _seed(database: Database, *, bgg_id: int = 340237, title: str = "Wonder Book",
          description: str | None = "A pop-up cooperative adventure.") -> int:
    now = datetime.now(UTC).isoformat()
    with database.transaction() as connection:
        board_game_id = int(connection.execute(
            """
            INSERT INTO board_games
                (bgg_id,title,item_type,min_players,max_players,bgg_average,
                 bgg_average_weight,created_at,updated_at)
            VALUES (?,?,'standalone',1,4,7.5,2.0,?,?)
            """,
            (bgg_id, title, now, now),
        ).lastrowid)
        connection.execute(
            """
            INSERT INTO board_game_enrichments
                (board_game_id,source,external_id,description,designers_json,
                 metadata_json,next_refresh_at,created_at,updated_at)
            VALUES (?,'bgg_xml_api2',?,?,'["Martino Chiacchiera"]',?,
                    '2099-01-01T00:00:00+00:00',?,?)
            """,
            (
                board_game_id,
                str(bgg_id),
                description,
                json.dumps({"mechanics": ["Cooperative Game"], "expansions": []}),
                now,
                now,
            ),
        )
    return board_game_id


def _service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outputs: list[str]):
    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    service = GameDescriptionService(database)
    calls: list[tuple[str, str]] = []

    def complete(system: str, prompt: str):
        calls.append((system, prompt))
        return _clean_output(outputs.pop(0)), "gemini", "gemini-test"

    monkeypatch.setattr(service, "_complete", complete)
    return database, service, calls


def test_generation_is_cached_and_survives_volatile_metadata(tmp_path, monkeypatch) -> None:
    database, service, calls = _service(tmp_path, monkeypatch, [GOOD])
    board_game_id = _seed(database)

    result = service.generate(340237)
    assert result["status"] == "ready"
    assert result["description"]["text"] == _clean_output(GOOD)
    assert "\n\n" in result["description"]["text"]
    payload = json.loads(calls[0][1])
    assert payload["opening_angle"] in OPENING_ANGLES
    assert payload["game"]["mechanics"] == ["Cooperative Game"]
    assert payload["game"]["publisher_description"] == "A pop-up cooperative adventure."

    with database.transaction() as connection:
        connection.execute(
            "UPDATE board_games SET bgg_average=8.1,bgg_average_weight=2.2 WHERE id=?",
            (board_game_id,),
        )
    assert service.generate(340237)["description"]["text"] == result["description"]["text"]
    assert len(calls) == 1

    with database.transaction() as connection:
        connection.execute(
            "UPDATE board_game_enrichments SET description='New text.' WHERE board_game_id=?",
            (board_game_id,),
        )
    assert service.status(340237)["status"] == "pending"


def test_promotional_or_labelled_draft_is_repaired(tmp_path, monkeypatch) -> None:
    bad = "Immergiti in Oniria! " + GOOD + "\n\nPunti forti: il pop-up."
    database, service, calls = _service(tmp_path, monkeypatch, [bad, GOOD])
    _seed(database)

    result = service.generate(340237)

    assert result["description"]["text"] == _clean_output(GOOD)
    assert len(calls) == 2
    assert "immergiti" in calls[1][0]
    assert "Punti forti" in calls[1][0]


def test_repeated_failure_is_not_stored(tmp_path, monkeypatch) -> None:
    database, service, _ = _service(tmp_path, monkeypatch, ["Troppo breve.", "Ancora breve."])
    _seed(database)

    with pytest.raises(GameDescriptionError, match="style checks"):
        service.generate(340237)
    assert service.status(340237)["status"] == "pending"


def test_recent_openings_of_other_games_are_avoided(tmp_path, monkeypatch) -> None:
    other = "Un libro pop-up domina il tavolo e guida tutto. " + GOOD
    database, service, calls = _service(tmp_path, monkeypatch, [GOOD, GOOD, other])
    _seed(database)
    _seed(database, bgg_id=381247, title="Dragon Eclipse")

    service.generate(340237)
    service.generate(381247)

    avoid = json.loads(calls[1][1])["avoid_openings"]
    assert avoid == [" ".join(_clean_output(GOOD).split()[:10])]
    assert len(calls) == 3  # identical opening triggered a repair


def test_missing_source_and_unknown_game(tmp_path, monkeypatch) -> None:
    database, service, _ = _service(tmp_path, monkeypatch, [])
    _seed(database, description=None)

    assert service.status(340237)["status"] == "missing_source"
    with pytest.raises(GameDescriptionError, match="No BGG description"):
        service.generate(340237)
    with pytest.raises(GameDescriptionError, match="not found"):
        service.status(1)


def test_style_checks_and_cleanup() -> None:
    assert _clean_output("**Titolo**\n\n- uno  due\n\n\n tre ") == "Titolo\n\nuno due\n\ntre"
    assert _style_problems(_clean_output(GOOD), title="Wonder Book", avoid_openings=[]) == []
    opening = "Wonder Book è un gioco cooperativo. " + GOOD
    assert any("titolo" in item for item in _style_problems(
        opening, title="Wonder Book", avoid_openings=[]))
    angles = {_opening_angle(bgg_id) for bgg_id in range(1, 200)}
    assert angles == set(OPENING_ANGLES)


def test_provider_fallback_order(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    service = GameDescriptionService(database)
    rag = SimpleNamespace(
        generation_provider="gemini",
        generation_provider_order=("gemini", "ollama"),
        gemini_generation_model="gemini-test",
        ollama_generation_model="local-test",
    )
    monkeypatch.setattr(
        "boardgamecompanion.game_description.resolve_rag_settings", lambda _db: rag
    )

    def fail(*_args):
        raise GameDescriptionError("Gemini unavailable")

    monkeypatch.setattr(service, "_gemini", fail)
    monkeypatch.setattr(service, "_ollama", lambda *_args: "Testo **locale**")

    assert service._complete("system", "prompt") == ("Testo locale", "ollama", "local-test")
