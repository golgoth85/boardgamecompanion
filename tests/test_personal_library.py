from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.dependencies import get_database
from boardgamecompanion.main import app
from boardgamecompanion.notifications import NotificationStore
from boardgamecompanion.settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    return TestClient(app)


def _import_fixture(client: TestClient) -> None:
    with FIXTURE.open("rb") as handle:
        response = client.post(
            "/api/imports/bgg-csv",
            files={"file": ("collection.csv", handle, "text/csv")},
        )
    assert response.status_code == 200


def test_personal_rating_and_played_state_are_distinct_from_completion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _import_fixture(client)
        updated = client.patch(
            "/api/games/900001/personal-state",
            json={"rating": 5, "played": True, "played_at": "2026-10-08"},
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["rating"] == 5
        assert body["played"] is True
        assert body["completed"] is False

        game = client.get("/api/games/900001").json()
        assert game["progress"]["rating"] == 5
        assert game["progress"]["played"] is True
        assert game["progress"]["completed"] is False

        trophy = client.get(
            "/api/games",
            params={"played": "true", "item_type": "standalone"},
        )
        assert trophy.status_code == 200
        assert 900001 in [item["bgg_id"] for item in trophy.json()["items"]]

        cleared = client.patch(
            "/api/games/900001/personal-state",
            json={"rating": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["rating"] is None


def test_wishlist_supports_bgg_and_crowdfunding_sources(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _import_fixture(client)
        bgg = client.post(
            "/api/wishlist",
            json={
                "source_kind": "bgg",
                "source_key": "123456",
                "bgg_id": 123456,
                "title": "Suggested Game",
                "year_published": 2026,
                "target_url": "https://boardgamegeek.com/boardgame/123456",
            },
        )
        assert bgg.status_code == 201

        campaign = client.post(
            "/api/wishlist",
            json={
                "source_kind": "crowdfunding",
                "source_key": "gamefound:campaign-1",
                "title": "Campaign Game",
                "target_url": "https://gamefound.com/example",
                "metadata": {"platform": "gamefound"},
            },
        )
        assert campaign.status_code == 201

        listing = client.get("/api/wishlist")
        assert listing.status_code == 200
        assert listing.json()["total"] == 2

        removed = client.delete(f"/api/wishlist/{campaign.json()['id']}")
        assert removed.status_code == 204
        assert client.get("/api/wishlist").json()["total"] == 1


def test_smart_and_manual_lists_share_catalog_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _import_fixture(client)
        client.patch(
            "/api/games/900001/personal-state",
            json={"rating": 4, "played": True},
        )
        smart = client.post(
            "/api/lists",
            json={
                "name": "Giocati e apprezzati",
                "kind": "smart",
                "filters": {
                    "played": True,
                    "personal_rating_min": 4,
                    "owned": True,
                },
            },
        )
        assert smart.status_code == 201
        resolved = client.get(f"/api/lists/{smart.json()['id']}/games")
        assert resolved.status_code == 200
        assert [item["bgg_id"] for item in resolved.json()["items"]] == [900001]

        manual = client.post(
            "/api/lists",
            json={"name": "Serata", "kind": "manual"},
        )
        assert manual.status_code == 201
        list_id = manual.json()["id"]
        assert client.put(f"/api/lists/{list_id}/items/900002").status_code == 204
        manual_games = client.get(f"/api/lists/{list_id}/games")
        assert [item["bgg_id"] for item in manual_games.json()["items"]] == [900002]


def test_notification_dedupe_and_read_state(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        store = NotificationStore(get_database())
        first = store.create_once(
            category="expansion",
            dedupe_key="expansion:900001:123",
            title="Nuova espansione",
            body="È uscita una nuova espansione rilevante.",
            target_url="/games/900001",
            related_bgg_id=900001,
        )
        second = store.create_once(
            category="expansion",
            dedupe_key="expansion:900001:123",
            title="Duplicato",
            body="Non deve creare una seconda notifica.",
            target_url="/games/900001",
            related_bgg_id=900001,
        )
        assert first["id"] == second["id"]
        listing = client.get("/api/notifications").json()
        assert listing["unread_count"] == 1
        marked = client.patch(
            f"/api/notifications/{first['id']}",
            json={"read": True},
        )
        assert marked.status_code == 200
        assert marked.json()["read"] is True
        assert client.get("/api/notifications").json()["unread_count"] == 0


def test_universal_search_has_extensible_groups(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _import_fixture(client)
        result = client.get("/api/search", params={"q": "alpha"})
        assert result.status_code == 200
        payload = result.json()
        assert payload["groups"]["games"][0]["bgg_id"] == 900001
        assert set(payload["groups"]) == {
            "games", "sections", "wishlist", "rulebooks", "crowdfunding"
        }
