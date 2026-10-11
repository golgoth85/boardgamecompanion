from __future__ import annotations

from pathlib import Path

import httpx

from boardgamecompanion.barcode_resolution import (
    BarcodeProductLookupError,
    BarcodeResolver,
    FallbackBarcodeLookup,
    UplayBarcodeLookup,
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
            "title": "Example Publisher Synthetic Alpha Board Game English Edition",
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
            "title": "Synthetic Alpha Board Game",
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



def test_fallback_lookup_uses_second_provider_after_primary_miss() -> None:
    primary = FakeLookup(product=None)
    secondary = FakeLookup(
        {
            "barcode": "3558380049463",
            "title": "La Leggenda dei Cinque Anelli: Il Gioco di Carte",
            "source": "uplay",
        }
    )

    product = FallbackBarcodeLookup(primary, secondary).lookup("3558380049463")

    assert product is not None
    assert product["source"] == "uplay"
    assert primary.calls == ["3558380049463"]
    assert secondary.calls == ["3558380049463"]


def _duckduckgo_search_result(product_url: str) -> str:
    from urllib.parse import quote

    return f"""
    <html><body>
      <a class="result__a"
         href="//duckduckgo.com/l/?uddg={quote(product_url, safe='')}">
        Board game result
      </a>
    </body></html>
    """


def _google_search_result(product_url: str) -> str:
    from urllib.parse import quote

    return f"""
    <html><body>
      <a href="/url?q={quote(product_url, safe='')}&sa=U">
        Board game result
      </a>
    </body></html>
    """


def test_uplay_lookup_resolves_known_italian_l5r_barcode() -> None:
    product_url = (
        "https://www.uplay.it/it/"
        "gioco-da-tavolo-la-leggenda-dei-cinque-anelli--il-gioco-di-carte.html"
    )
    product_html = """
    <html><body>
      <h1>La Leggenda dei Cinque Anelli: Il Gioco di Carte</h1>
      <div>Editore: Asmodee Italia</div>
      <div>Nomi alternativi:
        Legend of the Five Rings: The Card Game
        La Leggenda dei Cinque Anelli: Il Gioco di Carte
      </div>
      <div>BARCODE: 3558380049463</div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.uplay.it" and request.url.path == "/it/search":
            assert request.url.params["query"] == "3558380049463"
            return httpx.Response(200, text="<html>No barcode result</html>", request=request)
        if request.url.host == "www.google.com":
            assert "3558380049463" in request.url.params["q"]
            return httpx.Response(
                200,
                text=_google_search_result(product_url),
                request=request,
            )
        assert request.url.host == "www.uplay.it"
        assert "gioco-da-tavolo-la-leggenda-dei-cinque-anelli" in request.url.path
        return httpx.Response(200, text=product_html, request=request)

    lookup = UplayBarcodeLookup(transport=httpx.MockTransport(handler))
    product = lookup.lookup("3558380049463")

    assert product is not None
    assert product["barcode"] == "3558380049463"
    assert product["title"] == "La Leggenda dei Cinque Anelli: Il Gioco di Carte"
    assert product["source"] == "uplay"
    assert "Legend of the Five Rings: The Card Game" in product["description"]


def test_uplay_lookup_resolves_known_italian_verdant_barcode() -> None:
    product_url = "https://www.uplay.it/it/gioco-da-tavolo-verdant.html"
    product_html = """
    <html><body>
      <h1>Verdant</h1>
      <div>Editore: Oliphante</div>
      <div>BARCODE: 787790612193</div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.uplay.it" and request.url.path == "/it/search":
            assert request.url.params["query"] == "787790612193"
            return httpx.Response(200, text="<html>No barcode result</html>", request=request)
        if request.url.host == "www.google.com":
            assert "787790612193" in request.url.params["q"]
            return httpx.Response(503, request=request)
        if request.url.host == "html.duckduckgo.com":
            assert "787790612193" in request.url.params["q"]
            return httpx.Response(
                200,
                text=_duckduckgo_search_result(product_url),
                request=request,
            )
        assert request.url.host == "www.uplay.it"
        assert request.url.path.endswith("/gioco-da-tavolo-verdant.html")
        return httpx.Response(200, text=product_html, request=request)

    lookup = UplayBarcodeLookup(transport=httpx.MockTransport(handler))
    product = lookup.lookup("787790612193")

    assert product is not None
    assert product["barcode"] == "787790612193"
    assert product["title"] == "Verdant"
    assert product["source"] == "uplay"


def test_v3_negative_barcode_cache_is_ignored_after_provider_upgrade(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    barcode = "4000000000099"
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO app_settings(key,value,sensitive,updated_at)
            VALUES(?,?,0,CURRENT_TIMESTAMP)
            """,
            (
                f"barcode_product_lookup:v3:{barcode}",
                '{"schema_version":3,"product":null}',
            ),
        )

    lookup = FakeLookup(
        {
            "barcode": barcode,
            "title": "Synthetic Alpha Board Game",
            "brand": "Example Publisher",
            "category": "Toys & Games",
            "description": None,
            "images": [],
            "source": "upcitemdb",
        }
    )
    result = BarcodeResolver(database, product_lookup=lookup).lookup(barcode)

    assert lookup.calls == [barcode]
    assert result["resolution"] == "owned_game"
    assert result["external_lookup"] == "upcitemdb"
