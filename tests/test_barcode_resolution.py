from __future__ import annotations

from pathlib import Path

import httpx

from boardgamecompanion.barcode_resolution import (
    BarcodeProductLookupError,
    BarcodeResolver,
    FallbackBarcodeLookup,
    UplayBarcodeLookup,
    VerifiedBarcodeLookup,
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



def test_verified_catalog_resolves_known_l5r_without_network() -> None:
    network = FakeLookup(error=AssertionError("network fallback must not run"))
    product = FallbackBarcodeLookup(
        VerifiedBarcodeLookup(),
        network,
    ).lookup("3558380049463")

    assert product is not None
    assert product["bgg_id"] == 184151
    assert product["title"] == "La Leggenda dei Cinque Anelli: Il Gioco di Carte"
    assert product["source"] == "verified_catalog"
    assert network.calls == []


def test_verified_catalog_resolves_audited_italian_gtins_without_network() -> None:
    network = FakeLookup(error=AssertionError("network fallback must not run"))
    lookup = FallbackBarcodeLookup(VerifiedBarcodeLookup(), network)

    codenames = lookup.lookup("8034055580424")
    sagrada = lookup.lookup("8034055581032")

    assert codenames is not None
    assert codenames["bgg_id"] == 178900
    assert codenames["title"] == "Nome in Codice"
    assert codenames["source"] == "verified_catalog"

    assert sagrada is not None
    assert sagrada["bgg_id"] == 199561
    assert sagrada["title"] == "Sagrada"
    assert sagrada["source"] == "verified_catalog"
    assert network.calls == []


def test_verified_bgg_id_bypasses_fuzzy_title_matching(tmp_path: Path) -> None:
    database = _database(tmp_path)
    lookup = FakeLookup(
        {
            "barcode": "4000000000005",
            "bgg_id": 900001,
            "title": "Completely Different Localized Product Title",
            "brand": "Verified Publisher",
            "category": "Board Games",
            "description": None,
            "images": [],
            "source": "verified_catalog",
        }
    )

    result = BarcodeResolver(database, product_lookup=lookup).lookup(
        "4000000000005"
    )

    assert result["resolution"] == "owned_game"
    assert result["auto_match"]["bgg_id"] == 900001
    assert result["auto_match"]["confidence"] == 1.0
    assert result["external_lookup"] == "verified_catalog"


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


def test_v4_negative_barcode_cache_is_ignored_after_provider_upgrade(
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
                f"barcode_product_lookup:v4:{barcode}",
                '{"schema_version":4,"product":null}',
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


def test_resolver_continues_after_weak_primary_product(tmp_path: Path) -> None:
    database = _database(tmp_path)
    primary = FakeLookup(
        {
            "barcode": "4000000000100",
            "title": "Generic Product Cards Italian Edition",
            "brand": "Varie",
            "category": "Toys & Games",
            "description": None,
            "images": [],
            "source": "upcitemdb",
        }
    )
    secondary = FakeLookup(
        {
            "barcode": "4000000000100",
            "title": "Synthetic Alpha Board Game",
            "brand": "Example Publisher",
            "category": "Board Games",
            "description": "Synthetic Alpha",
            "images": [],
            "source": "uplay",
        }
    )

    result = BarcodeResolver(
        database,
        product_lookup=FallbackBarcodeLookup(primary, secondary),
    ).lookup("4000000000100")

    assert primary.calls == ["4000000000100"]
    assert secondary.calls == ["4000000000100"]
    assert result["resolution"] == "owned_game"
    assert result["external_lookup"] == "uplay"
    assert result["auto_match"]["bgg_id"] == 900001


def test_v5_negative_barcode_cache_is_ignored_after_provider_ranking_upgrade(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    barcode = "4000000000101"
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO app_settings(key,value,sensitive,updated_at)
            VALUES(?,?,0,CURRENT_TIMESTAMP)
            """,
            (
                f"barcode_product_lookup:v5:{barcode}",
                '{"schema_version":5,"product":null}',
            ),
        )

    lookup = FakeLookup(
        {
            "barcode": barcode,
            "title": "Synthetic Alpha Board Game",
            "brand": "Example Publisher",
            "category": "Board Games",
            "description": None,
            "images": [],
            "source": "uplay",
        }
    )
    result = BarcodeResolver(database, product_lookup=lookup).lookup(barcode)

    assert lookup.calls == [barcode]
    assert result["resolution"] == "owned_game"
    assert result["external_lookup"] == "uplay"


def _real_barcode_database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "real-barcode-catalog.sqlite3")
    database.initialize()
    BggCsvImporter(database).import_bytes(
        b"""objectid,objectname,originalname,own,collid,version_publishers
178900,Codenames,Codenames,1,810001,Cranio Creations
199561,Sagrada,Sagrada,1,810002,Cranio Creations
""",
        "real-barcodes.csv",
    )
    return database


def test_uplay_continues_after_discovered_page_fails_exact_barcode() -> None:
    stale_url = "https://www.uplay.it/it/gioco-da-tavolo-sagrada.html"
    exact_url = "https://www.uplay.it/en/gioco-da-tavolo-Nome-in-Codice.html"
    stale_html = """
    <html><body>
      <h1>Sagrada</h1>
      <div>BARCODE: 8034055585276</div>
    </body></html>
    """
    exact_html = """
    <html><body>
      <h1>Nome in Codice</h1>
      <div>Editore: Cranio Creations</div>
      <div>Nomi alternativi: Codenames Code Names</div>
      <div>BARCODE: 8034055580424</div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.uplay.it" and request.url.path == "/it/search":
            return httpx.Response(
                200,
                text=f'<html><a href="{stale_url}">stale result</a></html>',
                request=request,
            )
        if request.url.host == "www.google.com":
            assert "8034055580424" in request.url.params["q"]
            return httpx.Response(
                200,
                text=_google_search_result(exact_url),
                request=request,
            )
        if request.url.host == "www.uplay.it" and request.url.path.endswith(
            "/gioco-da-tavolo-sagrada.html"
        ):
            return httpx.Response(200, text=stale_html, request=request)
        if request.url.host == "www.uplay.it" and "Nome-in-Codice" in request.url.path:
            return httpx.Response(200, text=exact_html, request=request)
        raise AssertionError(f"unexpected request: {request.url}")

    product = UplayBarcodeLookup(
        transport=httpx.MockTransport(handler)
    ).lookup("8034055580424")

    assert product is not None
    assert product["barcode"] == "8034055580424"
    assert product["title"] == "Nome in Codice"
    assert product["source"] == "uplay"
    assert "Codenames" in product["description"]



def test_uplay_continues_to_public_index_for_real_sagrada_barcode() -> None:
    stale_url = "https://www.uplay.it/it/gioco-da-tavolo-sagrada--5---6-giocatore.html"
    exact_url = "https://www.uplay.it/it/gioco-da-tavolo-sagrada.html"
    stale_html = """
    <html><body>
      <h1>Sagrada: 5 &amp; 6 Giocatore</h1>
      <div>BARCODE: 8034055581698</div>
    </body></html>
    """
    exact_html = """
    <html><body>
      <h1>Sagrada</h1>
      <div>Editore: Cranio Creations</div>
      <div>Nomi alternativi: Sagrada</div>
      <div>BARCODE: 8034055581032</div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.uplay.it" and request.url.path == "/it/search":
            return httpx.Response(
                200,
                text=f'<html><a href="{stale_url}">stale result</a></html>',
                request=request,
            )
        if request.url.host == "www.google.com":
            assert "8034055581032" in request.url.params["q"]
            return httpx.Response(
                200,
                text=_google_search_result(exact_url),
                request=request,
            )
        if request.url.host == "www.uplay.it" and request.url.path.endswith(
            "/gioco-da-tavolo-sagrada--5---6-giocatore.html"
        ):
            return httpx.Response(200, text=stale_html, request=request)
        if request.url.host == "www.uplay.it" and request.url.path.endswith(
            "/gioco-da-tavolo-sagrada.html"
        ):
            return httpx.Response(200, text=exact_html, request=request)
        raise AssertionError(f"unexpected request: {request.url}")

    product = UplayBarcodeLookup(
        transport=httpx.MockTransport(handler)
    ).lookup("8034055581032")

    assert product is not None
    assert product["barcode"] == "8034055581032"
    assert product["title"] == "Sagrada"
    assert product["source"] == "uplay"

def test_real_codenames_pattern_prefers_later_exact_uplay_match(tmp_path: Path) -> None:
    database = _real_barcode_database(tmp_path)
    verified = FakeLookup(None)
    upc = FakeLookup(
        {
            "barcode": "8034055580424",
            "title": "Name In Code, Game Cards, By Cranio, Edition Italian",
            "brand": "Varie",
            "category": "Toys & Games > Games > Board Games",
            "description": None,
            "images": [],
            "source": "upcitemdb",
        }
    )
    uplay = FakeLookup(
        {
            "barcode": "8034055580424",
            "title": "Nome in Codice",
            "brand": "Cranio Creations",
            "category": "Board Games",
            "description": "Codenames Code Names",
            "images": [],
            "source": "uplay",
        }
    )
    retail = FakeLookup(error=AssertionError("retail fallback must not run"))

    result = BarcodeResolver(
        database,
        product_lookup=FallbackBarcodeLookup(verified, upc, uplay, retail),
    ).lookup("8034055580424")

    assert result["resolution"] == "owned_game"
    assert result["external_lookup"] == "uplay"
    assert result["auto_match"]["bgg_id"] == 178900
    assert verified.calls == ["8034055580424"]
    assert upc.calls == ["8034055580424"]
    assert uplay.calls == ["8034055580424"]
    assert retail.calls == []



def test_real_sagrada_pattern_falls_through_to_exact_uplay_match(tmp_path: Path) -> None:
    database = _real_barcode_database(tmp_path)
    verified = FakeLookup(None)
    upc = FakeLookup(None)
    uplay = FakeLookup(
        {
            "barcode": "8034055581032",
            "title": "Sagrada",
            "brand": "Cranio Creations",
            "category": "Board Games",
            "description": "Sagrada",
            "images": [],
            "source": "uplay",
        }
    )

    result = BarcodeResolver(
        database,
        product_lookup=FallbackBarcodeLookup(verified, upc, uplay),
    ).lookup("8034055581032")

    assert result["resolution"] == "owned_game"
    assert result["external_lookup"] == "uplay"
    assert result["auto_match"]["bgg_id"] == 199561
    assert verified.calls == ["8034055581032"]
    assert upc.calls == ["8034055581032"]
    assert uplay.calls == ["8034055581032"]

def test_v6_positive_cache_is_ignored_after_public_gtin_upgrade(tmp_path: Path) -> None:
    database = _real_barcode_database(tmp_path)
    barcode = "8034055580424"
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO app_settings(key,value,sensitive,updated_at)
            VALUES(?,?,0,CURRENT_TIMESTAMP)
            """,
            (
                f"barcode_product_lookup:v6:{barcode}",
                (
                    '{"schema_version":6,"product":'
                    '{"barcode":"8034055580424","title":"Name In Code, Game Cards, '
                    'By Cranio, Edition Italian","source":"upcitemdb"}}'
                ),
            ),
        )

    lookup = FakeLookup(
        {
            "barcode": barcode,
            "title": "Nome in Codice",
            "brand": "Cranio Creations",
            "description": "Codenames",
            "source": "uplay",
        }
    )
    result = BarcodeResolver(database, product_lookup=lookup).lookup(barcode)

    assert lookup.calls == [barcode]
    assert result["resolution"] == "owned_game"
    assert result["auto_match"]["bgg_id"] == 178900


def test_v6_negative_cache_is_ignored_after_public_gtin_upgrade(tmp_path: Path) -> None:
    database = _real_barcode_database(tmp_path)
    barcode = "8034055581032"
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO app_settings(key,value,sensitive,updated_at)
            VALUES(?,?,0,CURRENT_TIMESTAMP)
            """,
            (
                f"barcode_product_lookup:v6:{barcode}",
                '{"schema_version":6,"product":null}',
            ),
        )

    lookup = FakeLookup(
        {
            "barcode": barcode,
            "title": "Sagrada. Gioco da tavolo",
            "brand": "Cranio Creations",
            "source": "uplay",
        }
    )
    result = BarcodeResolver(database, product_lookup=lookup).lookup(barcode)

    assert lookup.calls == [barcode]
    assert result["resolution"] == "owned_game"
    assert result["auto_match"]["bgg_id"] == 199561


def test_v7_live_barcode_cache_is_ignored_after_verified_catalog_v8_upgrade(
    tmp_path: Path,
) -> None:
    database = _real_barcode_database(tmp_path)
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO app_settings(key,value,sensitive,updated_at)
            VALUES(?,?,0,CURRENT_TIMESTAMP)
            """,
            (
                "barcode_product_lookup:v7:8034055580424",
                (
                    '{"schema_version":7,"product":'
                    '{"barcode":"8034055580424","title":"Name In Code, Game Cards, '
                    'By Cranio, Edition Italian","source":"upcitemdb"}}'
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO app_settings(key,value,sensitive,updated_at)
            VALUES(?,?,0,CURRENT_TIMESTAMP)
            """,
            (
                "barcode_product_lookup:v7:8034055581032",
                '{"schema_version":7,"product":null}',
            ),
        )

    codenames = BarcodeResolver(database).lookup("8034055580424")
    sagrada = BarcodeResolver(database).lookup("8034055581032")

    assert codenames["resolution"] == "owned_game"
    assert codenames["external_lookup"] == "verified_catalog"
    assert codenames["auto_match"]["bgg_id"] == 178900
    assert codenames["auto_match"]["confidence"] == 1.0

    assert sagrada["resolution"] == "owned_game"
    assert sagrada["external_lookup"] == "verified_catalog"
    assert sagrada["auto_match"]["bgg_id"] == 199561
    assert sagrada["auto_match"]["confidence"] == 1.0
