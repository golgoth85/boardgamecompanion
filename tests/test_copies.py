from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.bgg_csv import BggCsvImporter
from boardgamecompanion.copies import PhysicalCopyStore
from boardgamecompanion.database import Database
from boardgamecompanion.main import app
from boardgamecompanion.settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def _fixture_with_updates(**updates: str) -> bytes:
    with FIXTURE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames

    rows[0].update(updates)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def test_bgg_import_creates_physical_copies_without_duplicates(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    importer = BggCsvImporter(database)

    importer.import_path(FIXTURE)
    importer.import_path(FIXTURE)

    store = PhysicalCopyStore(database)
    alpha = store.list_for_game(900001)
    beta = store.list_for_game(900002)

    assert len(alpha) == 1
    assert len(beta) == 1
    assert alpha[0]["source"] == {
        "kind": "bgg_csv",
        "collection_entry_id": 1,
        "copy_index": 1,
    }
    assert alpha[0]["barcode"] == "1234567890123"
    assert alpha[0]["barcode_normalized"] == "1234567890123"
    assert alpha[0]["language"] == "Italian"
    assert alpha[0]["publishers"] == "Example Publisher"
    assert alpha[0]["edition"] == "Retail IT"
    assert alpha[0]["inventory_location"] == "Kallax A1"


def test_later_import_adds_missing_quantity_without_overwriting_existing_copy(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    importer = BggCsvImporter(database)
    importer.import_path(FIXTURE)

    store = PhysicalCopyStore(database)
    first = store.list_for_game(900001)[0]
    store.update(
        first["id"],
        {
            "barcode": "CUSTOM-001",
            "inventory_location": "Custom Shelf",
            "notes": "Edited locally",
        },
    )

    importer.import_bytes(
        _fixture_with_updates(
            quantity="2",
            barcode="9999999999999",
            invlocation="CSV Shelf",
        ),
        "quantity-two.csv",
    )

    copies = store.list_for_game(900001)
    assert len(copies) == 2

    original = next(item for item in copies if item["source"]["copy_index"] == 1)
    added = next(item for item in copies if item["source"]["copy_index"] == 2)

    assert original["barcode"] == "CUSTOM-001"
    assert original["inventory_location"] == "Custom Shelf"
    assert original["notes"] == "Edited locally"

    assert added["barcode"] == "9999999999999"
    assert added["inventory_location"] == "CSV Shelf"
    assert added["source"]["kind"] == "bgg_csv"


def test_physical_copy_api_create_update_and_barcode_lookup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")

    with TestClient(app) as client:
        with FIXTURE.open("rb") as handle:
            imported = client.post(
                "/api/imports/bgg-csv",
                files={"file": ("collection.csv", handle, "text/csv")},
            )
        assert imported.status_code == 200

        existing = client.get("/api/games/900001/copies")
        assert existing.status_code == 200
        assert existing.json()["count"] == 1

        created = client.post(
            "/api/games/900001/copies",
            json={
                "barcode": "978-1 234-567",
                "language": "Italian",
                "edition": "Seconda copia",
                "inventory_location": "Kallax B4",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["source"]["kind"] == "manual"
        assert body["barcode_normalized"] == "9781234567"

        updated = client.patch(
            f"/api/copies/{body['id']}",
            json={
                "barcode": " 9781234567 ",
                "inventory_location": "Kallax C1",
                "notes": "Copia per prestiti",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["inventory_location"] == "Kallax C1"
        assert updated.json()["notes"] == "Copia per prestiti"

        lookup = client.post(
            "/api/barcodes/lookup",
            json={"barcode": "978-123-4567"},
        )
        assert lookup.status_code == 200
        result = lookup.json()
        assert result["normalized"] == "9781234567"
        assert result["count"] == 1
        assert result["matches"][0]["id"] == body["id"]
        assert result["matches"][0]["bgg_id"] == 900001

        all_copies = client.get("/api/games/900001/copies")
        assert all_copies.json()["count"] == 2

        missing_game = client.post(
            "/api/games/999999/copies",
            json={"barcode": "123"},
        )
        assert missing_game.status_code == 404
