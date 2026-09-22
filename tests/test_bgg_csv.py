from pathlib import Path

from boardgamecompanion.bgg_csv import BggCsvImporter
from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def test_import_is_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    importer = BggCsvImporter(database)

    first = importer.import_path(FIXTURE)
    second = importer.import_path(FIXTURE)

    assert first.row_count == 2
    assert first.created_count == 2
    assert first.updated_count == 0
    assert second.created_count == 0
    assert second.updated_count == 0
    assert second.unchanged_count == 2

    stats = Catalog(database).stats()
    assert stats == {"total": 2, "standalone": 1, "expansions": 1, "owned": 2}


def test_catalog_preserves_bgg_and_collection_fields(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggCsvImporter(database).import_path(FIXTURE)

    game = Catalog(database).get_game(900001)

    assert game is not None
    assert game["title"] == "Synthetic Alpha"
    assert game["bgg_id"] == 900001
    assert game["players"] == {"min": 2, "max": 4}
    assert game["bgg"]["average_weight"] == 2.2
    assert game["collection"]["barcode"] == "1234567890123"
    assert game["collection"]["inventory_location"] == "Kallax A1"
    assert game["collection"]["language"] == "Italian"


def test_catalog_search_and_filter(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggCsvImporter(database).import_path(FIXTURE)
    catalog = Catalog(database)

    result = catalog.list_games(query="beta", item_type="expansion", owned=True)

    assert result["total"] == 1
    assert result["items"][0]["bgg_id"] == 900002


def test_changed_export_updates_without_duplicates(tmp_path: Path) -> None:
    import csv
    import io

    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    importer = BggCsvImporter(database)
    importer.import_path(FIXTURE)

    with FIXTURE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames

    rows[0]["rating"] = "8.5"
    rows[0]["invlocation"] = "Kallax B2"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    result = importer.import_bytes(buffer.getvalue().encode("utf-8"), "collection-updated.csv")
    game = Catalog(database).get_game(900001)

    assert result.created_count == 0
    assert result.updated_count == 1
    assert result.unchanged_count == 1
    assert Catalog(database).stats()["total"] == 2
    assert game is not None
    assert game["collection"]["rating"] == 8.5
    assert game["collection"]["inventory_location"] == "Kallax B2"
