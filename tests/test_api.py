from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.main import app
from boardgamecompanion.settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def test_upload_and_catalog_api(tmp_path: Path) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"

    with TestClient(app) as client:
        with FIXTURE.open("rb") as handle:
            response = client.post(
                "/api/imports/bgg-csv",
                files={"file": ("collection.csv", handle, "text/csv")},
            )
        assert response.status_code == 200
        assert response.json()["created_count"] == 2

        stats = client.get("/api/catalog/stats")
        assert stats.status_code == 200
        assert stats.json()["total"] == 2

        games = client.get("/api/games", params={"q": "alpha"})
        assert games.status_code == 200
        assert games.json()["total"] == 1
        assert games.json()["items"][0]["bgg_id"] == 900001

        sorted_games = client.get("/api/games", params={"sort": "rating_desc"})
        assert sorted_games.status_code == 200
        assert sorted_games.json()["sort"] == "rating_desc"
        assert sorted_games.json()["items"][0]["bgg_id"] == 900001
