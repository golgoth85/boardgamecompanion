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


def test_rankings_api_modes_filters_and_acquisition_sort(tmp_path: Path) -> None:
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
            connection.execute(
                """
                UPDATE collection_entries
                SET acquisition_date='2026-10-01',user_rating=9.0,num_plays=0
                WHERE board_game_id=?
                """,
                (ids[900002],),
            )
            connection.execute(
                "UPDATE board_games SET bgg_rank=1200,bgg_bayes_average=7.2 WHERE bgg_id=900002"
            )
            for bgg_id, metadata in (
                (
                    900001,
                    {
                        "categories": ["Fantasy", "Adventure"],
                        "mechanics": ["Dice Rolling", "Hand Management"],
                    },
                ),
                (
                    900002,
                    {
                        "categories": ["Science Fiction"],
                        "mechanics": ["Deck Building"],
                    },
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
                        None,
                        json.dumps(metadata),
                        "2099-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )
            connection.execute(
                """
                INSERT INTO board_game_gameplay_summaries(
                    board_game_id,source_sha256,summary_text,provider,model,generated_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    ids[900001],
                    "synthetic",
                    "I giocatori lanciano dadi, gestiscono la propria mano e combinano risorse per completare obiettivi prima degli avversari.",
                    "gemini",
                    "test-model",
                    "2026-10-04T00:00:00+00:00",
                ),
            )

        overall = client.get("/api/catalog/rankings", params={"mode": "overall"})
        assert overall.status_code == 200
        assert overall.json()["mode"] == "overall"
        assert overall.json()["items"][0]["score"] > 0
        assert overall.json()["items"][0]["reason"]
        assert [
            item["score"] for item in overall.json()["items"]
        ] == sorted(
            [item["score"] for item in overall.json()["items"]],
            reverse=True,
        )
        assert all(
            not any(factor.casefold().startswith("qualità ") for factor in item["factors"])
            for item in overall.json()["items"]
        )
        assert all(
            any(factor.startswith("ideale in ") for factor in item["factors"])
            for item in overall.json()["items"]
        )
        alpha = next(
            item for item in overall.json()["items"]
            if item["game"]["bgg_id"] == 900001
        )
        assert alpha["game"]["gameplay_summary"].startswith("I giocatori lanciano dadi")

        for mode in (
            "outside_top",
            "quality_time",
            "gateway",
            "expert",
            "safe_choice",
            "personal_favorites",
        ):
            ranked = client.get("/api/catalog/rankings", params={"mode": mode})
            assert ranked.status_code == 200
            assert ranked.json()["mode"] == mode
            assert "description" in ranked.json()
            assert "items" in ranked.json()

        personal = client.get(
            "/api/catalog/rankings",
            params={"mode": "personal_favorites"},
        )
        assert personal.status_code == 200
        assert personal.json()["items"][0]["game"]["bgg_id"] == 900002

        outside = client.get(
            "/api/catalog/rankings",
            params={"mode": "outside_top"},
        )
        assert outside.status_code == 200
        assert outside.json()["title"] == "Fuori dalla Top 500"
        assert outside.json()["items"]
        assert all(
            int(item["game"]["bgg"]["rank"] or 0) > 500
            for item in outside.json()["items"]
        )
        assert all("rarità" not in item["reason"].casefold() for item in outside.json()["items"])

        fantasy = client.get(
            "/api/catalog/rankings",
            params={"mode": "overall", "category": "Fantasy"},
        )
        assert fantasy.status_code == 200
        assert [item["game"]["bgg_id"] for item in fantasy.json()["items"]] == [900001]

        newest = client.get(
            "/api/games",
            params={
                "owned": "true",
                "item_type": "standalone",
                "sort": "acquired_desc",
            },
        )
        assert newest.status_code == 200
        assert newest.json()["items"][0]["bgg_id"] == 900002
        assert newest.json()["items"][0]["collection"]["acquisition_date"] == "2026-10-01"

        completed = client.put(
            "/api/games/900001/completion",
            json={"completed": True, "completed_at": "2026-09-30"},
        )
        assert completed.status_code == 200
        assert completed.json()["progress"] == {
            "completed": True,
            "completed_at": "2026-09-30",
        }

        trophy = client.get(
            "/api/games",
            params={
                "owned": "true",
                "item_type": "standalone",
                "completed": "true",
                "sort": "completed_desc",
            },
        )
        assert trophy.status_code == 200
        assert [item["bgg_id"] for item in trophy.json()["items"]] == [900001]
        assert trophy.json()["items"][0]["progress"]["completed_at"] == "2026-09-30"

        stats = client.get("/api/catalog/stats")
        assert stats.status_code == 200
        assert stats.json()["completed"] == 1
        assert stats.json()["standalone_owned"] >= 1
        assert stats.json()["expansions_owned"] >= 0
        assert "rulebooks" in stats.json()

        uncompleted = client.put(
            "/api/games/900001/completion",
            json={"completed": False},
        )
        assert uncompleted.status_code == 200
        assert uncompleted.json()["progress"] == {
            "completed": False,
            "completed_at": None,
        }
        trophy_after = client.get("/api/games", params={"completed": "true"})
        assert trophy_after.status_code == 200
        assert trophy_after.json()["items"] == []


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
            connection.execute(
                "UPDATE board_games SET max_players=6 WHERE bgg_id=900002"
            )
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
        initial_player_options = {
            str(item["label"]): item["count"]
            for item in initial.json()["options"]["supports_players"]
        }
        assert initial_player_options["2"] == 2
        assert initial_player_options["4"] == 2
        assert initial_player_options["6+"] == 1

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

        filtered_player_labels = {
            item["label"] for item in payload["options"]["supports_players"]
        }
        assert "2" in filtered_player_labels
        assert "4" in filtered_player_labels
        assert "6+" not in filtered_player_labels

        self_excluding = client.get(
            "/api/catalog/explore",
            params=[
                ("category", "Fantasy"),
                ("supports_players", "6"),
            ],
        )
        assert self_excluding.status_code == 200
        self_payload = self_excluding.json()
        assert self_payload["total"] == 1
        six_plus = next(
            item
            for item in self_payload["options"]["supports_players"]
            if item["label"] == "6+"
        )
        assert six_plus["selected"] is True
        assert six_plus["count"] == 1
        assert any(
            item["label"] == "2"
            for item in self_payload["options"]["supports_players"]
        )

        incompatible = client.get(
            "/api/catalog/explore",
            params=[
                ("category", "Adventure"),
                ("mechanic", "Deck Building"),
            ],
        )
        assert incompatible.status_code == 200
        assert incompatible.json()["total"] == 0
