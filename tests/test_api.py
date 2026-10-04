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

        for sort_name, first_bgg_id in (
            ("title_desc", 900002),
            ("age_desc", 900002),
            ("duration_asc", 900002),
            ("weight_desc", 900001),
            ("rating_asc", 900002),
        ):
            sorted_column = client.get("/api/games", params={"sort": sort_name})
            assert sorted_column.status_code == 200
            assert sorted_column.json()["sort"] == sort_name
            assert sorted_column.json()["items"][0]["bgg_id"] == first_bgg_id

        players_sorted = client.get("/api/games", params={"sort": "players_asc"})
        assert players_sorted.status_code == 200
        assert players_sorted.json()["sort"] == "players_asc"

        advanced = client.get(
            "/api/games",
            params={
                "ideal_players": 2,
                "player_age": 12,
                "weight": "light",
                "max_minutes": 60,
                "min_rating": 7,
            },
        )
        assert advanced.status_code == 200
        assert advanced.json()["total"] == 1
        assert advanced.json()["items"][0]["bgg_id"] == 900002

        suitable_for_age_10 = client.get(
            "/api/games",
            params={"player_age": 10},
        )
        assert suitable_for_age_10.status_code == 200
        assert [item["bgg_id"] for item in suitable_for_age_10.json()["items"]] == [900001]
