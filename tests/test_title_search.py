from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.bgg_csv import BggCsvImporter
from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database
from boardgamecompanion.main import app
from boardgamecompanion.settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def _database_with_aliases(tmp_path: Path) -> Database:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggCsvImporter(database).import_path(FIXTURE)
    now = datetime.now(UTC).isoformat()
    metadata = json.dumps(
        {
            "alternate_titles": [
                "Codenames",
                "Nome in Codice",
                "Code Names",
            ]
        }
    )
    with database.transaction(immediate=True) as connection:
        game_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id=900001"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO board_game_enrichments(
                board_game_id,source,external_id,title,original_title,
                metadata_json,next_refresh_at,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                "bgg_xml_api2",
                "900001",
                "Synthetic Alpha Board Game",
                "Synthetic Alpha",
                metadata,
                "2099-01-01T00:00:00+00:00",
                now,
                now,
            ),
        )
    return database


def test_catalog_search_matches_localized_and_original_aliases(tmp_path: Path) -> None:
    database = _database_with_aliases(tmp_path)
    catalog = Catalog(database)

    english = catalog.list_games(query="codenames", limit=20)
    italian = catalog.list_games(query="nome in codice", limit=20)

    assert [item["bgg_id"] for item in english["items"]] == [900001]
    assert [item["bgg_id"] for item in italian["items"]] == [900001]


def test_universal_search_uses_bgg_alternate_titles(tmp_path: Path) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"

    with TestClient(app) as client:
        with FIXTURE.open("rb") as handle:
            imported = client.post(
                "/api/imports/bgg-csv",
                files={"file": ("collection.csv", handle, "text/csv")},
            )
        assert imported.status_code == 200

        database = Database(settings.database_path)
        now = datetime.now(UTC).isoformat()
        with database.transaction(immediate=True) as connection:
            game_id = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id=900001"
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO board_game_enrichments(
                    board_game_id,source,external_id,title,original_title,
                    metadata_json,next_refresh_at,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    game_id,
                    "bgg_xml_api2",
                    "900001",
                    "Synthetic Alpha Board Game",
                    "Synthetic Alpha",
                    json.dumps(
                        {"alternate_titles": ["Codenames", "Nome in Codice"]}
                    ),
                    "2099-01-01T00:00:00+00:00",
                    now,
                    now,
                ),
            )

        for query in ("codenames", "nome in codice"):
            response = client.get("/api/search", params={"q": query})
            assert response.status_code == 200
            games = response.json()["groups"]["games"]
            assert [item["bgg_id"] for item in games] == [900001]
