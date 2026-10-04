import json
from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.main import app, get_database
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


def test_explore_api_intersects_multiple_facets_and_contextual_counts(tmp_path: Path) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"

    csv_payload = FIXTURE.read_text(encoding="utf-8").replace(
        ",expansion,,,,,,,,1,,,,,English,2021,",
        ",standalone,,,,,,,,1,,,,,English,2021,",
    ).encode("utf-8")

    with TestClient(app) as client:
        response = client.post(
            "/api/imports/bgg-csv",
            files={"file": ("collection.csv", csv_payload, "text/csv")},
        )
        assert response.status_code == 200

        database = get_database()
        with database.transaction(immediate=True) as connection:
            rows = connection.execute(
                "SELECT id,bgg_id FROM board_games ORDER BY bgg_id"
            ).fetchall()
            ids = {int(row["bgg_id"]): int(row["id"]) for row in rows}
            for bgg_id, metadata, cover in (
                (
                    900001,
                    {
                        "categories": ["Fantasy", "Adventure"],
                        "mechanics": ["Dice Rolling", "Hand Management"],
                    },
                    "https://example.test/alpha.jpg",
                ),
                (
                    900002,
                    {
                        "categories": ["Fantasy", "Science Fiction"],
                        "mechanics": ["Dice Rolling", "Deck Building"],
                    },
                    "https://example.test/beta.jpg",
                ),
            ):
                connection.execute(
                    """
                    INSERT INTO board_game_enrichments(
                        board_game_id,source,external_id,title,cover_url,
                        metadata_json,next_refresh_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ids[bgg_id],
                        "test",
                        str(bgg_id),
                        f"Game {bgg_id}",
                        cover,
                        json.dumps(metadata),
                        "2099-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )

        initial = client.get("/api/catalog/explore")
        assert initial.status_code == 200
        assert initial.json()["total"] == 2
        fantasy = next(
            item for item in initial.json()["categories"] if item["name"] == "Fantasy"
        )
        assert fantasy["count"] == 2
        assert fantasy["covers"] == [
            "https://example.test/alpha.jpg",
            "https://example.test/beta.jpg",
        ]

        filtered = client.get(
            "/api/catalog/explore",
            params=[
                ("category", "Fantasy"),
                ("category", "Adventure"),
                ("mechanic", "Dice Rolling"),
            ],
        )
        assert filtered.status_code == 200
        payload = filtered.json()
        assert payload["total"] == 1
        assert [game["bgg_id"] for game in payload["games"]] == [900001]
        assert payload["filters"]["categories"] == ["Fantasy", "Adventure"]
        assert payload["filters"]["mechanics"] == ["Dice Rolling"]

        hand_management = next(
            item
            for item in payload["mechanics"]
            if item["name"] == "Hand Management"
        )
        assert hand_management["count"] == 1
        assert hand_management["selected"] is False

        incompatible = client.get(
            "/api/catalog/explore",
            params=[
                ("category", "Adventure"),
                ("mechanic", "Deck Building"),
            ],
        )
        assert incompatible.status_code == 200
        assert incompatible.json()["total"] == 0
