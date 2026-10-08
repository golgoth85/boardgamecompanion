from __future__ import annotations

import json
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
            "games", "sections", "wishlist", "lists", "rulebooks", "crowdfunding"
        }


def test_diagnostics_centralizes_technical_state(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        payload = client.get("/api/diagnostics")
        assert payload.status_code == 200
        body = payload.json()
        assert body["schema_version"] == 19
        assert set(body) == {
            "schema_version",
            "bgg",
            "assistant",
            "crowdfunding",
            "suggestions",
            "rulebooks",
            "personal",
        }
        assert "cache" in body["suggestions"]
        assert "generation_order" in body["assistant"]
        assert "expansion_scans" in body["personal"]


def test_universal_search_finds_documents_lists_and_cached_campaigns(
    monkeypatch, tmp_path: Path,
) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _import_fixture(client)
        db = get_database()
        with db.transaction() as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id=900001"
            ).fetchone()
            connection.execute(
                """
                INSERT INTO game_documents (
                    id,board_game_id,document_type,language,title,
                    original_filename,storage_path,sha256,size_bytes,
                    mime_type,source_kind,is_official,provenance_json,
                    created_at,updated_at
                ) VALUES (
                    'search-document',?,'rulebook','it','Regolamento Alpha',
                    'alpha-rules.pdf','900001/alpha-rules.pdf',?,200,
                    'application/pdf','manual_upload',1,'{}',
                    'now','now'
                )
                """,
                (game["id"], "a" * 64),
            )
        saved_list = client.post(
            "/api/lists",
            json={"name": "Alpha evening", "kind": "manual"},
        )
        assert saved_list.status_code == 201
        settings.crowdfunding_cache_path.write_text(
            json.dumps({
                "schema_version": 2,
                "campaigns": [{
                    "id": "gamefound:alpha",
                    "title": "Alpha: The Campaign",
                    "platform": "gamefound",
                    "project_url": "https://gamefound.com/alpha",
                }],
            }),
            encoding="utf-8",
        )

        result = client.get("/api/search", params={"q": "alpha"})
        assert result.status_code == 200
        groups = result.json()["groups"]
        assert groups["games"][0]["bgg_id"] == 900001
        assert groups["rulebooks"][0]["id"] == "search-document"
        assert groups["rulebooks"][0]["url"] == "/api/documents/search-document/file"
        assert groups["lists"][0]["id"] == saved_list.json()["id"]
        assert groups["crowdfunding"][0]["id"] == "gamefound:alpha"

        wildcard = client.get("/api/search", params={"q": "%"})
        assert wildcard.status_code == 200
        assert wildcard.json()["groups"]["rulebooks"] == []


def test_smart_list_rejects_invalid_filter_types_and_ranges(
    monkeypatch, tmp_path: Path,
) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _import_fixture(client)
        cases = [
            {"owned": "false"},
            {"played": 1},
            {"supports_players": "two"},
            {"personal_rating_min": 6},
            {"personal_rating_min": 5, "personal_rating_max": 2},
            {"min_rating": "good"},
            {"weight": "impossible"},
            {"sort": "not_an_order"},
            {"category": ["deck building"]},
        ]
        for filters in cases:
            response = client.post(
                "/api/lists",
                json={"name": "Invalid list", "kind": "smart", "filters": filters},
            )
            assert response.status_code == 400, (filters, response.text)

        manual = client.post(
            "/api/lists",
            json={"name": "Manual", "kind": "manual", "filters": {"owned": True}},
        )
        assert manual.status_code == 400
        assert client.get("/api/lists").json()["total"] == 0


def test_manual_list_rejects_known_but_unowned_games(
    monkeypatch, tmp_path: Path,
) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _import_fixture(client)
        with get_database().transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE collection_entries
                SET own=0
                WHERE board_game_id=(SELECT id FROM board_games WHERE bgg_id=900002)
                """
            )
        manual = client.post(
            "/api/lists",
            json={"name": "Solo posseduti", "kind": "manual"},
        )
        assert manual.status_code == 201
        rejected = client.put(
            f"/api/lists/{manual.json()['id']}/items/900002"
        )
        assert rejected.status_code == 400
        assert "owned" in rejected.json()["detail"].casefold()


def test_wishlist_rejects_non_http_links(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        unsafe_values = (
            "javascript:alert(1)",
            "https://user:pass@example.com/private",
            "https://exa mple.com/campaign",
            "https://[broken",
            "https://example.com:bad/campaign",
        )
        for field in ("target_url", "cover_url"):
            for index, value in enumerate(unsafe_values):
                payload = {
                    "source_kind": "crowdfunding",
                    "source_key": f"unsafe-{field}-{index}",
                    "title": "Unsafe campaign",
                    field: value,
                }
                response = client.post("/api/wishlist", json=payload)
                assert response.status_code == 400
                assert field in response.json()["detail"]
