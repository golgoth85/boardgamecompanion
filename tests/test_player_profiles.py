from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.database import Database
from boardgamecompanion.players import PlayerError, PlayerProfiles
from boardgamecompanion.plays import PlayLog

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()


@pytest.fixture()
def database(tmp_path: Path) -> Database:
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


def test_profile_links_history_by_name_and_alias_without_rewriting_plays(database: Database) -> None:
    log = PlayLog(database)
    log.create(1, {"played_on": "2026-10-01", "play_mode": "competitive",
                   "players": [{"name": "Raffi", "winner": True}, {"name": "Marco"}]})
    log.create(2, {"played_on": "2026-10-02", "play_mode": "cooperative", "outcome": "won",
                   "players": [{"name": "raffaella"}, {"name": "Ospite"}]})
    with database.connect() as connection:
        before = [row[0] for row in connection.execute("SELECT players_json FROM game_plays ORDER BY id")]
    profiles = PlayerProfiles(database)
    raffa = profiles.create({"name": "Raffaella", "aliases": ["Raffi"], "description": "Strategia"})
    assert log.list(player_id=raffa["id"])["total"] == 2
    assert log.list(player="RAFFI")["total"] == 2
    listed = log.list()["items"]
    assert {p["name"]: p["profile_id"] for p in listed[1]["players"]} == {"Raffi": raffa["id"], "Marco": None}
    summary = log.summary()
    assert summary["players"][0] == {"name": "Raffaella", "profile_id": raffa["id"], "plays": 2, "wins": 2}
    overview = log.player_overview(raffa["id"])
    assert overview["totals"]["plays"] == 2 and overview["totals"]["wins"] == 2 and overview["totals"]["decided"] == 2
    assert {item["name"] for item in overview["companions"]} == {"Marco", "Ospite"}
    defaults = log.defaults()
    assert "Raffi" not in defaults["guest_names"] and "Ospite" in defaults["guest_names"]
    assert defaults["profiles"][0]["name"] == "Raffaella"
    # Rinominare conserva il nome precedente come alias; eliminare il profilo non tocca le partite.
    renamed = profiles.update(raffa["id"], {"name": "Raffa"})
    assert set(renamed["aliases"]) == {"Raffi", "Raffaella"}
    profiles.delete(raffa["id"])
    with database.connect() as connection:
        after = [row[0] for row in connection.execute("SELECT players_json FROM game_plays ORDER BY id")]
    assert after == before


def test_profile_names_are_unique_across_aliases_and_accents(database: Database) -> None:
    profiles = PlayerProfiles(database)
    profiles.create({"name": "Élsa", "aliases": ["Elsina"]})
    for values in ({"name": "élsa"}, {"name": "Anna", "aliases": ["ELSINA"]}):
        with pytest.raises(PlayerError):
            profiles.create(values)
    PlayLog(database).create(1, {"played_on": "2026-10-01", "players": [{"name": "ÉLSA"}]})
    elsa = profiles.list()[0]
    assert PlayLog(database).list(player_id=elsa["id"])["total"] == 1


def test_photo_validation(database: Database) -> None:
    profiles = PlayerProfiles(database)
    marco = profiles.create({"name": "Marco"})
    with pytest.raises(PlayerError):
        profiles.set_photo(marco["id"], "data:image/png;base64," + base64.b64encode(b"\xff\xd8\xff").decode())
    with pytest.raises(PlayerError):
        profiles.set_photo(marco["id"], "data:image/svg+xml;base64,PHN2Zz4=")
    updated = profiles.set_photo(marco["id"], JPEG)
    assert updated["has_photo"] and updated["photo_version"]
    content, kind = profiles.photo(marco["id"])
    assert kind == "image/jpeg" and content.startswith(b"\xff\xd8\xff")
    assert not profiles.clear_photo(marco["id"])["has_photo"]


def test_stats_periods_split_session_time_and_navigate(database: Database) -> None:
    log = PlayLog(database)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    log.create(1, {"played_on": monday.isoformat(), "duration_minutes": 90, "location": "Casa",
                   "play_mode": "competitive", "players": [{"name": "Marco", "winner": True}, {"name": "Emma"}]})
    log.create_session(2, {"request_id": "a" * 32, "played_on": monday.isoformat(), "duration_minutes": 60,
                           "play_mode": "cooperative", "players": [{"name": "Marco"}, {"name": "Emma"}],
                           "rounds": [{"outcome": "won"}, {"outcome": "lost"}, {"outcome": "lost"}]})
    old = (monday - timedelta(days=40)).isoformat()
    log.create(1, {"played_on": old, "duration_minutes": 30, "players": [{"name": "Emma"}]})

    week = log.stats(period="week", anchor=today.isoformat())
    assert week["start"] == monday.isoformat() and len(week["series"]) == 7
    assert week["totals"] == {"plays": 4, "minutes": 150, "games": 2, "days": 1, "players": 2, "wins": 0, "decided": 0}
    assert week["series"][0]["plays"] == 4 and week["series"][0]["minutes"] == 150
    assert week["next_anchor"] is None and week["prev_anchor"]
    assert [game["bgg_id"] for game in week["games"]] == [2, 1]
    assert week["games"][0]["minutes"] == 60
    assert week["locations"] == [{"name": "Casa", "plays": 1}]

    marco = log.stats(period="all", player="marco")
    assert marco["totals"]["plays"] == 4 and marco["totals"]["wins"] == 2 and marco["totals"]["decided"] == 4
    day = log.stats(period="day", anchor=old)
    assert day["totals"]["plays"] == 1 and day["series"] == [] and day["next_anchor"]
    assert log.stats(period="year", anchor=today.isoformat())["series"][today.month - 1]["plays"] >= 4
    with pytest.raises(Exception):
        log.stats(period="decade")


def test_player_api(database: Database, monkeypatch) -> None:
    from boardgamecompanion import main
    from boardgamecompanion.routers import plays as plays_router

    monkeypatch.setattr(plays_router, "get_database", lambda: database)
    client = TestClient(main.app)
    created = client.post("/api/players", json={"name": "Emma", "description": "Ama i cooperativi"})
    assert created.status_code == 201
    player_id = created.json()["id"]
    assert client.post("/api/players", json={"name": "emma"}).status_code == 400
    assert client.put(f"/api/players/{player_id}/photo", json={"data_url": JPEG}).json()["has_photo"]
    photo = client.get(f"/api/players/{player_id}/photo")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/players/{player_id}").json()["profile"]["name"] == "Emma"
    assert client.patch(f"/api/players/{player_id}", json={"color": "#3987e5"}).json()["color"] == "#3987e5"
    assert client.patch(f"/api/players/{player_id}", json={"color": "#000000"}).status_code == 400
    assert client.get("/api/plays/stats?period=week").status_code == 200
    assert client.get("/api/plays/stats?period=decade").status_code == 422
    assert client.get("/plays/players/1").status_code == 200
    assert client.delete(f"/api/players/{player_id}").status_code == 204
    assert client.get(f"/api/players/{player_id}").status_code == 404


def test_db_backup_copies_consistently_and_never_overwrites(database: Database, tmp_path: Path) -> None:
    from boardgamecompanion.db_backup import backup

    PlayLog(database).create(1, {"played_on": "2026-10-01"})
    target = tmp_path / "backups" / "copy.sqlite3"
    result = backup(database.path, target)
    assert result["integrity"] == "ok" and result["plays"] == 1 and result["schema"] == database.schema_version()
    with pytest.raises(SystemExit):
        backup(database.path, target)
