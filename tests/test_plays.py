from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.database import Database
from boardgamecompanion.personal_state import PersonalStateStore
from boardgamecompanion.plays import PlayError, PlayLog, PlayNotFound
from boardgamecompanion.plays import suggested_play_mode


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    now = datetime.now(UTC).isoformat()
    with database.transaction(immediate=True) as connection:
        for bgg_id, title in ((1, "Gloomhaven"), (2, "Sky Team")):
            connection.execute(
                "INSERT INTO board_games(bgg_id,title,source_metadata_json,created_at,updated_at) VALUES(?,?,'{}',?,?)",
                (bgg_id, title, now, now),
            )
    return database


def test_play_log_records_sessions_and_syncs_progress(tmp_path: Path) -> None:
    database = _database(tmp_path)
    log = PlayLog(database)
    first = log.create(1, {
        "played_on": "2026-10-01",
        "players": [{"name": "Marco", "score": "42", "winner": True}, {"name": "Giulia"}, {"name": " "}],
        "activity": "Scenario 3",
        "outcome": "won",
        "duration_minutes": 120,
    })
    assert first["player_count"] == 2
    assert first["players"][0] == {"name": "Marco", "score": "42", "winner": True, "profile_id": None}
    assert first["activity"] == "Scenario 3"
    state = PersonalStateStore(database).get(1)
    assert state["played"] and state["played_at"] == "2026-10-01" and not state["completed"]

    log.create(1, {"played_on": "2026-10-10", "players": [{"name": "marco"}], "completed_game": True})
    state = PersonalStateStore(database).get(1)
    assert state["played_at"] == "2026-10-10" and state["completed_at"] == "2026-10-10"
    # An older play never moves the last played date back.
    log.create(1, {"played_on": "2026-09-01"})
    assert PersonalStateStore(database).get(1)["played_at"] == "2026-10-10"

    listed = log.list(bgg_id=1)
    assert listed["total"] == 3
    assert [item["played_on"] for item in listed["items"]] == ["2026-10-10", "2026-10-01", "2026-09-01"]
    assert log.list(player="MARCO")["total"] == 2
    assert log.list(q="scenario")["total"] == 1

    summary = log.summary()
    assert summary["plays"] == 3 and summary["games"] == 1 and summary["minutes"] == 120
    assert summary["players"][0] == {"name": "Marco", "profile_id": None, "plays": 2, "wins": 1}
    assert summary["games_played"][0]["won"] == 1

    updated = log.update(first["id"], {"notes": "Tesa fino all'ultimo", "outcome": None})
    assert updated["notes"] == "Tesa fino all'ultimo" and updated["outcome"] is None
    assert updated["activity"] == "Scenario 3"
    log.delete(first["id"])
    with pytest.raises(PlayNotFound):
        log.get(first["id"])
    latest = log.list(bgg_id=1)["items"][0]
    log.delete(latest["id"])
    assert PersonalStateStore(database).get(1)["played_at"] == "2026-09-01"


def test_play_defaults_copy_last_play_of_game_then_any(tmp_path: Path) -> None:
    database = _database(tmp_path)
    log = PlayLog(database)
    assert log.defaults(1)["last_play"] is None
    log.create(2, {"played_on": "2026-10-02", "players": [{"name": "Anna"}, {"name": "Luca"}], "location": "Casa"})
    log.create(1, {"played_on": "2026-10-01", "players": [{"name": "Marco"}], "activity": "Capitolo 1"})

    same = log.defaults(1)
    assert same["same_game"] and same["last_play"]["activity"] == "Capitolo 1"
    other = log.defaults(None)
    assert not other["same_game"] and other["last_play"]["bgg_id"] == 2
    assert set(other["player_names"]) == {"Anna", "Luca", "Marco"}
    assert other["locations"] == ["Casa"]


def test_play_validation(tmp_path: Path) -> None:
    log = PlayLog(_database(tmp_path))
    with pytest.raises(PlayError):
        log.create(1, {})
    with pytest.raises(PlayError):
        log.create(1, {"played_on": (date.today() + timedelta(days=1)).isoformat()})
    with pytest.raises(PlayError):
        log.create(1, {"played_on": "2026-10-01", "outcome": "maybe"})
    with pytest.raises(PlayNotFound):
        log.create(99, {"played_on": "2026-10-01"})


def test_play_api(tmp_path: Path, monkeypatch) -> None:
    from boardgamecompanion.main import app
    from boardgamecompanion.routers import plays as router

    database = _database(tmp_path)
    monkeypatch.setattr(router, "get_database", lambda: database)
    client = TestClient(app)
    created = client.post("/api/games/1/plays", json={
        "played_on": "2026-10-01",
        "players": [{"name": "Marco", "winner": True}],
        "notes": "Ottima",
    })
    assert created.status_code == 201
    play_id = created.json()["id"]
    assert client.get("/api/plays").json()["total"] == 1
    assert client.get("/api/plays/summary").json()["plays"] == 1
    assert client.get("/api/plays/defaults?bgg_id=1").json()["last_play"]["notes"] == "Ottima"
    assert client.patch(f"/api/plays/{play_id}", json={"duration_minutes": 45}).json()["duration_minutes"] == 45
    assert client.post("/api/games/1/plays", json={"played_on": "01/10/2026"}).status_code == 422
    assert client.post("/api/games/99/plays", json={"played_on": "2026-10-01"}).status_code == 404
    assert client.delete(f"/api/plays/{play_id}").status_code == 204
    assert client.delete(f"/api/plays/{play_id}").status_code == 404


def test_plays_page_and_old_address_serve_the_app() -> None:
    from boardgamecompanion.main import app

    client = TestClient(app)
    for path in ("/plays", "/completed"):
        response = client.get(path)
        assert response.status_code == 200 and "text/html" in response.headers["content-type"]


@pytest.mark.parametrize(("metadata", "expected"), [
    ({"mechanics": ["Cooperative Game", "Hand Management"]}, "cooperative"),
    ({"mechanics": ["Set Collection"]}, "competitive"),
    ({"mechanics": ["Cooperative Game", "Traitor Game"]}, None),
    ({"mechanics": ["Semi-Cooperative Game"]}, None),
    ({}, None), ({"mechanics": []}, None), ("invalid json", None),
])
def test_suggested_mode_uses_mechanics_without_guessing_mixed_games(metadata, expected):
    assert suggested_play_mode(metadata) == expected


def test_modes_and_count_updates_preserve_historical_data(tmp_path: Path) -> None:
    database = _database(tmp_path)
    log = PlayLog(database)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO board_game_enrichments(board_game_id,source,external_id,metadata_json,fetched_at,"
            "next_refresh_at,created_at,updated_at) VALUES(1,'bgg','1',?,?,'2099-01-01','2026-01-01','2026-01-01')",
            ('{"mechanics":["Cooperative Game"]}', datetime.now(UTC).isoformat()),
        )
    assert log.defaults(1)["suggested_mode"] == "cooperative"
    assert log.defaults(2)["suggested_mode"] is None
    old = log.create(1, {
        "played_on": "2026-10-01", "players": [{"name": "Anna", "winner": True}],
        "player_count": 4, "outcome": "won", "notes": "Storico",
    })
    assert old["play_mode"] == "cooperative"
    log.create(1, {
        "played_on": "2026-10-02", "play_mode": "cooperative", "outcome": "lost",
        "players": [{"name": "Anna", "winner": True}, {"name": "Luca"}],
    })
    log.create(1, {
        "played_on": "2026-10-03", "play_mode": "cooperative", "outcome": "won",
        "players": [{"name": "Anna"}, {"name": "Luca"}],
    })
    summary = {item["name"]: item for item in log.summary()["players"]}
    assert summary["Anna"]["wins"] == 2
    assert summary["Luca"]["wins"] == 1
    updated = log.update(old["id"], {"play_mode": "competitive"})
    assert updated["play_mode"] == "competitive"
    for field in ("players", "player_count", "outcome", "notes", "played_on"):
        assert updated[field] == old[field]
    updated = log.update(old["id"], {"players": [{"name": "Anna"}, {"name": "Luca"}]})
    assert updated["player_count"] == 2
    assert log.update(old["id"], {"notes": "Aggiornato"})["player_count"] == 2
    assert log.update(old["id"], {"player_count": 5})["player_count"] == 5
    with pytest.raises(PlayError):
        log.update(old["id"], {"play_mode": "invalid"})


def test_mode_migration_preserves_all_session_columns(tmp_path: Path) -> None:
    database = _database(tmp_path)
    play = PlayLog(database).create(1, {
        "played_on": "2026-10-01", "players": [{"name": "Anna", "score": "10", "winner": True}],
        "player_count": 4, "outcome": "won", "activity": "Capitolo 17", "notes": "Da conservare",
        "duration_minutes": 60, "location": "Casa", "completed_game": True,
    })
    with database.transaction() as connection:
        connection.execute("ALTER TABLE game_plays DROP COLUMN play_mode")
        connection.execute("DELETE FROM schema_migrations WHERE version=28")
        before = tuple(connection.execute("SELECT * FROM game_plays WHERE id=?", (play["id"],)).fetchone())
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        after = tuple(connection.execute("SELECT * FROM game_plays WHERE id=?", (play["id"],)).fetchone())
        assert after[:-1] == before and after[-1] is None
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
