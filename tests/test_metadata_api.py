from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import boardgamecompanion.main as main_module
from boardgamecompanion.main import app
from boardgamecompanion.settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def configure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")


def provider_payload(bgg_id: int = 900001) -> dict:
    return {
        "id": None,
        "media_id": str(bgg_id),
        "source": "bgg",
        "source_url": f"https://boardgamegeek.com/boardgame/{bgg_id}",
        "media_type": "boardgame",
        "title": "Synthetic Alpha provider",
        "image": "https://cf.geekdo-images.com/alpha.jpg",
        "synopsis": "Fresh provider synopsis.",
        "genres": ["Strategy", "Economic"],
        "score": 8.3,
        "score_count": 5000,
        "details": {
            "year": "2024",
            "players": "1-5 players",
            "playtime": "45 min",
            "min_age": "12+",
            "designers": "A. Designer",
            "publishers": "Provider Publisher",
        },
    }
class StubFloppy:
    def __init__(self, payload: dict | None) -> None:
        self.payload = payload
        self.calls: list[int] = []

    def boardgame_bgg_provider_detail(self, bgg_id: int):
        self.calls.append(bgg_id)
        return self.payload


def import_fixture(client: TestClient) -> None:
    with FIXTURE.open("rb") as handle:
        response = client.post(
            "/api/imports/bgg-csv",
            files={"file": ("collection.csv", handle, "text/csv")},
        )
    assert response.status_code == 200


def test_refresh_metadata_persists_cache_without_overwriting_csv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    stub = StubFloppy(provider_payload())
    monkeypatch.setattr(main_module, "get_floppy_client", lambda: stub)

    with TestClient(app) as client:
        import_fixture(client)

        refreshed = client.post("/api/games/900001/metadata/refresh")
        assert refreshed.status_code == 200
        assert refreshed.json()["changed"] is True
        assert refreshed.json()["metadata"]["score"] == 8.3
        assert stub.calls == [900001]

        second = client.post("/api/games/900001/metadata/refresh")
        assert second.status_code == 200
        assert second.json()["changed"] is False

        monkeypatch.setattr(main_module, "get_floppy_client", lambda: None)
        cached = client.get("/api/games/900001")
    assert cached.status_code == 200
    game = cached.json()
    assert game["title"] == "Synthetic Alpha"
    assert game["year_published"] == 2020
    assert game["bgg"]["average"] == 7.8
    assert game["metadata"]["image_url"] == "https://cf.geekdo-images.com/alpha.jpg"
    assert game["metadata"]["year_published"] == 2024
    assert game["metadata"]["publishers"] == "Provider Publisher"


def test_refresh_metadata_checks_local_game_before_floppy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    stub = StubFloppy(provider_payload(999999))
    monkeypatch.setattr(main_module, "get_floppy_client", lambda: stub)

    with TestClient(app) as client:
        response = client.post("/api/games/999999/metadata/refresh")

    assert response.status_code == 404
    assert stub.calls == []


def test_refresh_metadata_requires_floppy_configuration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setattr(main_module, "get_floppy_client", lambda: None)

    with TestClient(app) as client:
        import_fixture(client)
        response = client.post("/api/games/900001/metadata/refresh")

    assert response.status_code == 409
    assert "Floppy is not configured" in response.json()["detail"]
def test_refresh_metadata_rejects_provider_identity_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    wrong = provider_payload(900002)
    stub = StubFloppy(wrong)
    monkeypatch.setattr(main_module, "get_floppy_client", lambda: stub)

    with TestClient(app) as client:
        import_fixture(client)
        response = client.post("/api/games/900001/metadata/refresh")
        game = client.get("/api/games/900001")

    assert response.status_code == 502
    assert "identity does not match" in response.json()["detail"]
    assert game.status_code == 200
    assert game.json()["metadata"] is None


def test_refresh_metadata_reports_provider_not_found(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    stub = StubFloppy(None)
    monkeypatch.setattr(main_module, "get_floppy_client", lambda: stub)

    with TestClient(app) as client:
        import_fixture(client)
        response = client.post("/api/games/900001/metadata/refresh")

    assert response.status_code == 404
    assert response.json()["detail"] == "BGG metadata was not found through Floppy"
