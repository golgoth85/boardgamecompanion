from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from boardgamecompanion.bgg_csv import BggCsvImporter
from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database
from boardgamecompanion.metadata import (
    GameMetadataInvalidProviderPayload,
    GameMetadataStore,
)

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def provider_payload(bgg_id: int = 900001) -> dict:
    return {
        "id": None,
        "media_id": str(bgg_id),
        "source": "bgg",
        "source_url": f"https://boardgamegeek.com/boardgame/{bgg_id}",
        "media_type": "boardgame",
        "title": "Synthetic Alpha — provider",
        "image": "https://cf.geekdo-images.com/example.jpg",
        "synopsis": "Provider description.",
        "genres": ["Strategy", "Strategy", "Economic"],
        "score": 8.1,
        "score_count": 1234,
        "tracked": False,
        "details": {
            "year": "2024",
            "players": "1-5 players",
            "playtime": "45 min",
            "min_age": "12+",
            "designers": "A. Designer",
            "publishers": "Provider Publisher",
        },
    }
def database_with_fixture(tmp_path: Path) -> Database:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggCsvImporter(database).import_path(FIXTURE)
    return database


def test_metadata_cache_is_separate_from_csv_and_idempotent(tmp_path: Path) -> None:
    database = database_with_fixture(tmp_path)
    store = GameMetadataStore(database)
    first_time = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)

    metadata, changed = store.upsert_from_floppy(
        900001,
        provider_payload(),
        now=first_time,
    )

    assert changed is True
    assert metadata["image_url"] == "https://cf.geekdo-images.com/example.jpg"
    assert metadata["genres"] == ["Strategy", "Economic"]
    assert metadata["score"] == 8.1
    assert metadata["players"] == "1-5 players"
    assert metadata["fetched_at"] == first_time.isoformat()

    game = Catalog(database).get_game(900001)
    assert game is not None
    assert game["title"] == "Synthetic Alpha"
    assert game["year_published"] == 2020
    assert game["bgg"]["average"] == 7.8
    assert game["metadata"]["title"] == "Synthetic Alpha — provider"
    assert game["metadata"]["year_published"] == 2024
    second_time = first_time + timedelta(hours=1)
    same, changed = store.upsert_from_floppy(
        900001,
        provider_payload(),
        now=second_time,
    )
    assert changed is False
    assert same["fetched_at"] == second_time.isoformat()
    assert same["updated_at"] == first_time.isoformat()

    changed_payload = provider_payload()
    changed_payload["score"] = 8.2
    updated, changed = store.upsert_from_floppy(
        900001,
        changed_payload,
        now=second_time + timedelta(hours=1),
    )
    assert changed is True
    assert updated["score"] == 8.2
    assert updated["updated_at"] == (second_time + timedelta(hours=1)).isoformat()

    game_after = Catalog(database).get_game(900001)
    assert game_after is not None
    assert game_after["title"] == "Synthetic Alpha"
    assert game_after["year_published"] == 2020
    assert game_after["bgg"]["average"] == 7.8


def test_metadata_cache_rejects_wrong_provider_identity(tmp_path: Path) -> None:
    database = database_with_fixture(tmp_path)
    payload = provider_payload()
    payload["media_id"] = "900002"

    with pytest.raises(
        GameMetadataInvalidProviderPayload,
        match="identity does not match",
    ):
        GameMetadataStore(database).upsert_from_floppy(900001, payload)


def test_metadata_cache_drops_non_http_urls_and_survives_corrupt_genres(
    tmp_path: Path,
) -> None:
    database = database_with_fixture(tmp_path)
    payload = provider_payload()
    payload["image"] = "ftp://example.test/image.jpg"
    payload["source_url"] = "file:///tmp/game"
    metadata, _ = GameMetadataStore(database).upsert_from_floppy(900001, payload)

    assert metadata["image_url"] is None
    assert metadata["source_url"] is None

    with database.connect() as connection:
        connection.execute(
            """
            UPDATE game_metadata_cache
            SET genres_json = '{'
            WHERE provider = 'floppy_bgg'
            """
        )

    cached = GameMetadataStore(database).get_for_game(900001)
    assert cached is not None
    assert cached["genres"] == []

    game = Catalog(database).get_game(900001)
    assert game is not None
    assert game["metadata"]["genres"] == []
