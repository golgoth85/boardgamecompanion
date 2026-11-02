from __future__ import annotations

import json
from pathlib import Path

import httpx

from boardgamecompanion.barcode_ai import (
    AiBarcodeLookup,
    DeepSeekBarcodeIdentifier,
    GeminiBarcodeIdentifier,
)
from boardgamecompanion.barcode_resolution import BarcodeResolver
from boardgamecompanion.bgg_csv import BggCsvImporter
from boardgamecompanion.database import Database

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"
BARCODE = "8058697270765"
PAGE_URL = "https://shop.example.com/il-regno-di-valiria"


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggCsvImporter(database).import_path(FIXTURE)
    return database


def _add_reference_game(database: Database) -> None:
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO bgg_reference_games(
                bgg_id,name,year_published,is_expansion,rank,average,users_rated,
                source,created_at,updated_at,alt_names
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                170561,
                "Valeria: Card Kingdoms",
                2016,
                0,
                675,
                7.42801,
                6517,
                "dump",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                "Il Regno di Valiria",
            ),
        )


class FakeDeepSeekClient:
    def __init__(self, page: str, result: dict | None) -> None:
        self.page = page
        self.result = result
        self.searches: list[dict] = []
        self.fetches: list[dict] = []
        self.extractions: list[dict] = []

    def request(self, method: str, path: str, payload=None):
        if path == "v1/tools/search":
            self.searches.append(payload)
            return {
                "results": [
                    {
                        "url": PAGE_URL,
                        "title": "Il Regno di Valiria",
                        "content": self.page,
                        "snippet": self.page,
                    }
                ]
            }
        if path == "v1/tools/fetch":
            self.fetches.append(payload)
            assert payload["url"] == PAGE_URL
            return {"url": PAGE_URL, "title": "Il Regno di Valiria", "content": self.page}
        raise AssertionError(f"unexpected request {path}")

    def structured(self, system: str, payload, *, schema=None):
        self.extractions.append(payload)
        return self.result


def _identification(**overrides) -> dict:
    value = {
        "barcode": BARCODE,
        "title": "Il Regno di Valiria",
        "brand": "Ghenos Games",
        "original_title": "Valeria: Card Kingdoms",
        "bgg_id": 170561,
        "evidence_url": PAGE_URL,
        "evidence_quote": f"BARCODE: {BARCODE}",
    }
    value.update(overrides)
    return value


def test_deepseek_identifier_extracts_only_from_pages_with_the_exact_barcode() -> None:
    page = (
        "<html><body><h1>Il Regno di Valiria</h1>"
        f"<div>Editore: Ghenos Games · BARCODE: {BARCODE}</div>"
        "</body></html>"
    )
    client = FakeDeepSeekClient(page, _identification())
    identifier = DeepSeekBarcodeIdentifier(client)

    product = identifier.identify(BARCODE)

    assert product is not None
    assert product["title"] == "Il Regno di Valiria"
    assert product["original_title"] == "Valeria: Card Kingdoms"
    assert product["bgg_id"] == 170561
    assert product["source"] == "deepseek_search"
    assert product["requires_review"] is True
    assert client.searches[0]["query"] == f'"{BARCODE}"'
    assert BARCODE in client.extractions[0]["pages"][0]["content"]


def test_deepseek_identifier_rejects_a_page_without_the_barcode() -> None:
    client = FakeDeepSeekClient(
        "<html><body><h1>Il Regno di Valiria</h1><div>BARCODE: 0000000000000</div></body></html>",
        _identification(),
    )

    assert DeepSeekBarcodeIdentifier(client).identify(BARCODE) is None
    assert client.extractions == []


def test_deepseek_identifier_rejects_an_unquoted_evidence_claim() -> None:
    page = (
        "<html><body><h1>Il Regno di Valiria</h1>"
        f"<div>BARCODE: {BARCODE}</div></body></html>"
    )
    client = FakeDeepSeekClient(
        page,
        _identification(evidence_quote="Un passaggio che non esiste"),
    )

    assert DeepSeekBarcodeIdentifier(client).identify(BARCODE) is None


def test_ai_lookup_accepts_a_bgg_id_only_when_the_catalogued_names_match(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _add_reference_game(database)

    class Identifier:
        source = "deepseek_search"

        def identify(self, barcode: str):
            return _identification()

    product = AiBarcodeLookup(database, Identifier()).lookup(BARCODE)

    assert product is not None
    assert product["bgg_id"] == 170561
    assert product["requires_review"] is True

    class WrongIdentifier(Identifier):
        def identify(self, barcode: str):
            return _identification(bgg_id=1)

    wrong = AiBarcodeLookup(database, WrongIdentifier()).lookup(BARCODE)

    assert wrong is not None
    assert "bgg_id" not in wrong


def test_ai_product_does_not_auto_match_an_unowned_board_game(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO board_games(bgg_id,title,item_type,created_at,updated_at)
            VALUES(?,?,?,?,?)
            """,
            (900003, "Synthetic Gamma", "standalone", "2026-01-01", "2026-01-01"),
        )

    class Lookup:
        def lookup(self, barcode: str):
            return {
                "barcode": barcode,
                "bgg_id": 900003,
                "title": "Synthetic Gamma",
                "source": "deepseek_search",
                "requires_review": True,
            }

    result = BarcodeResolver(database, product_lookup=Lookup()).lookup(BARCODE)

    assert result["resolution"] == "product_identified"
    assert result["auto_match"] is None
    assert result["candidates"] == []
    assert 900003 not in {item["bgg_id"] for item in result["candidates"]}


def test_identified_product_offers_reference_catalog_titles(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _add_reference_game(database)

    class Lookup:
        def lookup(self, barcode: str):
            return {
                "barcode": barcode,
                "bgg_id": 170561,
                "title": "Il Regno di Valiria",
                "description": "Valeria: Card Kingdoms",
                "source": "deepseek_search",
                "requires_review": True,
            }

    result = BarcodeResolver(database, product_lookup=Lookup()).lookup(BARCODE)

    assert result["resolution"] == "product_identified"
    assert [item["bgg_id"] for item in result["reference_candidates"]] == [170561]
    assert result["reference_candidates"][0]["name"] == "Valeria: Card Kingdoms"


def test_v8_negative_cache_is_ignored_after_ai_provider_upgrade(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO app_settings(key,value,sensitive,updated_at)
            VALUES(?,?,0,CURRENT_TIMESTAMP)
            """,
            (
                f"barcode_product_lookup:v8:{BARCODE}",
                '{"schema_version":8,"product":null}',
            ),
        )

    class Lookup:
        def lookup(self, barcode: str):
            return {
                "barcode": barcode,
                "title": "Il Regno di Valiria",
                "source": "deepseek_search",
                "requires_review": True,
            }

    result = BarcodeResolver(database, product_lookup=Lookup()).lookup(BARCODE)

    assert result["resolution"] == "product_identified"
    assert result["external_lookup"] == "deepseek_search"


def _gemini_payload(result: dict, grounded_url: str) -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": json.dumps(result)}]},
                "groundingMetadata": {
                    "groundingChunks": [{"web": {"uri": grounded_url, "title": "Shop"}}]
                },
            }
        ]
    }


def _gemini_identifier(payload: dict) -> GeminiBarcodeIdentifier:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret"
        body = json.loads(request.content)
        assert body["tools"] == [{"googleSearch": {}}]
        return httpx.Response(200, json=payload)

    return GeminiBarcodeIdentifier(
        base_url="https://generativelanguage.googleapis.com",
        api_key="secret",
        model="gemini-3.5-flash-lite",
        client=httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            transport=httpx.MockTransport(handler),
        ),
    )


def test_gemini_identifier_requires_a_grounded_evidence_url() -> None:
    payload = _gemini_payload(_identification(), PAGE_URL)

    product = _gemini_identifier(payload).identify(BARCODE)

    assert product is not None
    assert product["source"] == "gemini_search"
    assert product["source_url"] == PAGE_URL

    ungrounded = _gemini_payload(_identification(), "https://other.example.com/page")
    assert _gemini_identifier(ungrounded).identify(BARCODE) is None


def test_gemini_identifier_rejects_a_different_barcode() -> None:
    payload = _gemini_payload(_identification(barcode="0000000000000"), PAGE_URL)

    assert _gemini_identifier(payload).identify(BARCODE) is None
