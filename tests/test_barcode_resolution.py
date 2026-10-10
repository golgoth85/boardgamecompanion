from __future__ import annotations

from pathlib import Path

from boardgamecompanion.barcode_resolution import (
    BarcodeProductLookupError,
    BarcodeResolver,
)
from boardgamecompanion.bgg_csv import BggCsvImporter
from boardgamecompanion.database import Database

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


class FakeLookup:
    def __init__(self, product=None, error: Exception | None = None) -> None:
        self.product = product
        self.error = error
        self.calls: list[str] = []

    def lookup(self, barcode: str):
        self.calls.append(barcode)
        if self.error is not None:
            raise self.error
        return self.product


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggCsvImporter(database).import_path(FIXTURE)
    return database


def test_existing_local_barcode_does_not_call_external_lookup(tmp_path: Path) -> None:
    database = _database(tmp_path)
    lookup = FakeLookup(
        {"title": "Should not be used", "source": "upcitemdb"}
    )

    result = BarcodeResolver(database, product_lookup=lookup).lookup(
        "1234567890123"
    )

    assert result["resolution"] == "local_copy"
    assert result["count"] == 1
    assert lookup.calls == []


def test_unknown_barcode_resolves_owned_game_from_product_title(tmp_path: Path) -> None:
    database = _database(tmp_path)
    lookup = FakeLookup(
        {
            "barcode": "4000000000001",
            "title": "Example Publisher Alpha Game Board Game English Edition",
            "brand": "Example Publisher",
            "category": "Toys & Games",
            "description": "Tabletop strategy game",
            "images": [],
            "source": "upcitemdb",
        }
    )

    result = BarcodeResolver(database, product_lookup=lookup).lookup(
        "4000000000001"
    )

    assert result["count"] == 0
    assert result["resolution"] == "owned_game"
    assert result["auto_match"]["bgg_id"] == 900001
    assert result["auto_match"]["confidence"] >= 0.82
    assert result["product"]["source"] == "upcitemdb"


def test_external_result_is_cached_in_app_settings(tmp_path: Path) -> None:
    database = _database(tmp_path)
    lookup = FakeLookup(
        {
            "barcode": "4000000000002",
            "title": "Alpha Game Board Game",
            "brand": "Example Publisher",
            "category": "Toys & Games",
            "description": None,
            "images": [],
            "source": "upcitemdb",
        }
    )
    resolver = BarcodeResolver(database, product_lookup=lookup)

    first = resolver.lookup("4000000000002")
    second = resolver.lookup("4000000000002")

    assert first["auto_match"]["bgg_id"] == 900001
    assert second["auto_match"]["bgg_id"] == 900001
    assert lookup.calls == ["4000000000002"]
    assert second["external_lookup"] == "cache"


def test_ambiguous_product_does_not_auto_assign(tmp_path: Path) -> None:
    database = _database(tmp_path)
    lookup = FakeLookup(
        {
            "barcode": "4000000000003",
            "title": "Generic Strategy Board Game",
            "brand": "Unknown",
            "category": "Toys & Games",
            "description": None,
            "images": [],
            "source": "upcitemdb",
        }
    )

    result = BarcodeResolver(database, product_lookup=lookup).lookup(
        "4000000000003"
    )

    assert result["auto_match"] is None
    assert result["resolution"] == "product_identified"


def test_external_lookup_failure_keeps_manual_fallback_available(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    lookup = FakeLookup(
        error=BarcodeProductLookupError("UPCitemdb rate limit reached")
    )

    result = BarcodeResolver(database, product_lookup=lookup).lookup(
        "4000000000004"
    )

    assert result["resolution"] == "unresolved"
    assert result["external_lookup"] == "failed"
    assert "rate limit" in result["external_error"].lower()
