from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.database import Database
from boardgamecompanion.personal_state import PersonalStateStore
from boardgamecompanion.plays import PlayError, PlayLog, PlayNotFound


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
    assert first["players"][0] == {"name": "Marco", "score": "42", "winner": True}
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
    assert summary["players"][0] == {"name": "Marco", "plays": 2, "wins": 1}
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
