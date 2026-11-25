from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.italian_rulebook_search import (
    SEARCH_KEY,
    ItalianRulebookProvider,
    ItalianRulebookSearchService,
    filename_language,
    italian_edition,
    text_language,
)
from boardgamecompanion.rulebook_discovery import RulebookDiscoveryService
from boardgamecompanion.rulebook_providers import RuleBookOrgProvider
from boardgamecompanion.rulebooks import RulebookProviderError, RulebookQuery

ITALIAN_TEXT = (
    "Il gioco si svolge in turni. Ogni giocatore pesca una carta e poi deve scegliere "
    "una delle azioni della plancia. Quando il mazzo finisce la partita termina e il "
    "giocatore con più punti vince. Per preparare il gioco, mescolate le carte e date "
    "cinque carte a ogni giocatore. Le carte sono divise per colore e il primo giocatore "
    "è chi ha giocato per ultimo. Con due giocatori si usano anche le regole della variante."
)
ENGLISH_TEXT = (
    "The game is played over several turns. Each player draws a card and then must choose "
    "one of the actions on the board. When the deck runs out the game ends and the player "
    "with the most points wins. To set up the game, shuffle the cards and deal five cards to "
    "each player. The cards are divided by color and the first player is the one who played "
    "this game last. With two players you also use the variant rules from this booklet."
)


def test_language_from_file_names_and_text() -> None:
    assert filename_language("https://x.it/files/Sagrada_Regolamento_ITA.pdf") == "it"
    assert filename_language("https://x.it/files/sagrada-rulebook.pdf") == "en"
    assert filename_language("https://x.it/it/sagrada.pdf") == "it"
    assert filename_language("https://x.it/files/sagrada.pdf") is None
    assert filename_language("https://x.it/files/sagrada-regles.pdf") == "fr"
    assert filename_language("https://x.it/files/sagrada-rules-eng-ita.pdf") is None
    assert text_language(ITALIAN_TEXT) == "it"
    assert text_language(ENGLISH_TEXT) == "en"
    assert text_language("troppo corto") is None


def test_italian_edition_from_versions() -> None:
    versions = [
        {"name": "Sagrada", "languages": ["Italian"], "publishers": ["dV Giochi"]},
        {"name": "Sagrada", "languages": ["English"], "publishers": ["Floodgate Games"]},
    ]
    assert italian_edition(versions) == ("Sagrada", ("dV Giochi",))


class FakeWeb:
    def __init__(self, results: dict[str, list[dict]], pages: dict[str, dict]):
        self.results = results
        self.pages = pages
        self.searches: list[str] = []
        self.fetches: list[str] = []

    def search(self, query: str, count: int = 6) -> list[dict]:
        self.searches.append(query)
        for key, value in self.results.items():
            if key in query:
                return value
        return []

    def fetch(self, item: dict) -> dict:
        self.fetches.append(item["url"])
        return self.pages[item["url"]]


def provider_with(web: FakeWeb) -> ItalianRulebookProvider:
    provider = ItalianRulebookProvider.__new__(ItalianRulebookProvider)
    provider.web = web
    return provider


QUERY = RulebookQuery(
    bgg_id=199561,
    title="Sagrada",
    italian_title="Sagrada",
    italian_publishers=("dV Giochi S.r.l.",),
)


def test_provider_keeps_only_italian_pdfs_of_the_game() -> None:
    web = FakeWeb(
        {
            "regolamento italiano pdf": [
                {"url": "https://www.dvgiochi.com/catalogo/sagrada/", "title": "Sagrada", "content": "", "snippet": ""},
                {"url": "https://files.example.com/Sagrada_rulebook_EN.pdf", "title": "Sagrada rulebook", "content": "", "snippet": ""},
                {"url": "https://files.example.com/Azul_regolamento.pdf", "title": "Azul regolamento", "content": "", "snippet": ""},
            ],
        },
        {
            "https://www.dvgiochi.com/catalogo/sagrada/": {
                "url": "https://www.dvgiochi.com/catalogo/sagrada/",
                "title": "Sagrada - dV Giochi",
                "content": ITALIAN_TEXT
                + " Scarica https://www.dvgiochi.com/wp-content/uploads/sagrada.pdf"
                + " e https://www.dvgiochi.com/wp-content/uploads/sagrada-rules-en.pdf",
            },
        },
    )
    candidates = provider_with(web).discover(QUERY)

    assert [item.url for item in candidates] == ["https://www.dvgiochi.com/wp-content/uploads/sagrada.pdf"]
    candidate = candidates[0]
    assert candidate.language == "it" and candidate.confidence == 40 and not candidate.official
    assert candidate.metadata["search_language"] == "it"
    assert any("dV Giochi" in query and "S.r.l" not in query for query in web.searches)
    assert any("site:boardgamegeek.com" in query for query in web.searches)


def test_provider_errors_are_reported_without_candidates() -> None:
    from boardgamecompanion.cloud_ai import CloudAIError

    class Broken(FakeWeb):
        def search(self, query: str, count: int = 6) -> list[dict]:
            raise CloudAIError("quota")

    with pytest.raises(RulebookProviderError):
        provider_with(Broken({}, {})).discover(QUERY)


def seed(database: Database) -> None:
    now = datetime.now(UTC).isoformat()
    with database.transaction() as connection:
        for bgg_id, title, language in ((199561, "Sagrada", "en"), (13, "Catan", "it"), (14, "Senza", None)):
            connection.execute(
                """INSERT INTO board_games(bgg_id,title,item_type,source_metadata_json,created_at,updated_at)
                   VALUES (?,?,'boardgame','{}',?,?)""",
                (bgg_id, title, now, now),
            )
            game_id = connection.execute("SELECT id FROM board_games WHERE bgg_id=?", (bgg_id,)).fetchone()[0]
            connection.execute(
                """INSERT INTO collection_entries(board_game_id,own,source_metadata_json,created_at,updated_at)
                   VALUES (?,1,'{}',?,?)""",
                (game_id, now, now),
            )
            connection.execute(
                """INSERT INTO board_game_enrichments(board_game_id,source,external_id,metadata_json,
                       next_refresh_at,created_at,updated_at)
                   VALUES (?,'bgg',?,?,?,?,?)""",
                (game_id, str(bgg_id), json.dumps({"italian_title": f"{title} IT"}), now, now, now),
            )
            if language:
                connection.execute(
                    """INSERT INTO game_documents(id,board_game_id,document_type,language,title,original_filename,
                           storage_path,sha256,size_bytes,source_kind,is_official,created_at,updated_at)
                       VALUES (?,?,'rulebook',?,'Rules','rules.pdf',?,?,1,'manual_upload',0,?,?)""",
                    (f"doc-{bgg_id}", game_id, language, f"/tmp/{bgg_id}.pdf", "a" * 64, now, now),
                )


def test_service_lists_games_without_italian_and_queues_candidates(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    seed(database)
    discovery = RulebookDiscoveryService(database, ())
    query = discovery.query_for(199561)
    assert query.italian_title == "Sagrada IT"

    web = FakeWeb(
        {"Sagrada IT": [{"url": "https://files.example.com/Sagrada_IT_regolamento.pdf", "title": "Sagrada IT", "content": "", "snippet": ""}]},
        {},
    )
    service = ItalianRulebookSearchService(
        database,
        provider_with(web),
        query_for=discovery.query_for,
        versions=lambda bgg_id: [{"name": "Sagrada", "languages": ["Italian"], "publishers": ["dV Giochi"]}],
    )
    items = service.games_without_italian()
    assert [(item["bgg_id"], item["languages"], item["last_italian_search_at"]) for item in items] == [(199561, ["en"], None)]

    result = service.search(199561)

    assert result["candidates_found"] == 1 and result["review_items_created"] == 1
    assert result["italian_title"] == "Sagrada IT" and result["italian_publishers"] == ["dV Giochi"]
    assert result["review_items"][0]["status"] == "pending"
    after = service.games_without_italian()[0]
    assert after["pending_italian"] == 1 and after["last_italian_search_at"]
    with database.connect() as connection:
        stored = connection.execute(
            "SELECT metadata_json FROM board_game_enrichments e JOIN board_games g ON g.id=e.board_game_id WHERE g.bgg_id=199561"
        ).fetchone()[0]
    assert SEARCH_KEY in json.loads(stored)


def test_service_without_web_provider_explains_configuration(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    service = ItalianRulebookSearchService(database, None, query_for=lambda bgg_id: QUERY)
    with pytest.raises(RulebookProviderError, match="DeepSeek"):
        service.search(199561)


def test_rulebook_org_null_results_mean_no_match() -> None:
    class Http:
        def get(self, url, *, allowed_hosts):
            class Response:
                content = b'{"results": null}'

            return Response()

    assert RuleBookOrgProvider(Http()).discover(QUERY) == ()


def test_official_italian_sites_run_first_and_skip_the_web(tmp_path: Path) -> None:
    from boardgamecompanion.rulebooks import RulebookCandidate, RulebookSource

    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    seed(database)
    discovery = RulebookDiscoveryService(database, ())

    class Official:
        name = "official_site_cranio_creations"

        def __init__(self) -> None:
            self.queries: list[RulebookQuery] = []

        def discover(self, query: RulebookQuery):
            self.queries.append(query)
            return (
                RulebookCandidate(
                    provider=self.name, source_kind=RulebookSource.OFFICIAL_LOCALIZER,
                    url="https://www.craniocreations.it/storage/Sagrada_ITA_Rules.pdf", language="it",
                    official=True, confidence=90, title="Sagrada — Rules", game_title="Sagrada",
                ),
                RulebookCandidate(
                    provider=self.name, source_kind=RulebookSource.OFFICIAL_LOCALIZER,
                    url="https://www.craniocreations.it/storage/Sagrada_EN_Rules.pdf", language="en",
                    official=True, confidence=90, title="Sagrada — Rules", game_title="Sagrada",
                ),
            )

    class Broken:
        name = "official_site_down"

        def discover(self, query):
            raise RulebookProviderError("down")

    official = Official()
    web = FakeWeb({}, {})
    service = ItalianRulebookSearchService(
        database, provider_with(web), query_for=discovery.query_for,
        versions=lambda bgg_id: [{"name": "Sagrada", "languages": ["Italian"], "publishers": ["Cranio Creations"]}],
        official_providers=(Broken(), official),
    )
    result = service.search(199561)

    assert official.queries[0].italian_publishers == ("Cranio Creations",)
    assert result["candidates_found"] == 1 and result["review_items"][0]["official"]
    assert result["failures"][0]["provider"] == "official_site_down"
    assert web.searches == [] and result["queries"] == []


def test_publisher_site_reads_italian_from_the_pdf_name() -> None:
    from boardgamecompanion.official_site_discovery import VERIFIED_PUBLISHER_SITES, PublisherSiteProvider, PublisherSiteResolver

    site = next(item for item in VERIFIED_PUBLISHER_SITES if item.key == "cranio_creations")
    query = RulebookQuery(bgg_id=199561, title="Sagrada", italian_publishers=("Cranio Creations",))
    assert PublisherSiteResolver((site,)).resolve(query) == (site,)
    candidate = PublisherSiteProvider(site)._candidate(
        query, page_url="https://craniocreations.it/products/sagrada", title="Sagrada",
        pdf_url="https://www.craniocreations.it/storage/media/Sagrada_ITA_Rules_compressed.pdf",
        label="Scarica PDF", bgg_ids=set(), product_context=True,
    )
    assert candidate is not None and candidate.language == "it" and candidate.official


def test_pdf_mentioning_the_game_in_its_body_is_not_its_rulebook() -> None:
    web = FakeWeb(
        {"regolamento italiano pdf": [{
            "url": "https://www.example.it/uploads/elenco-giochi-in-ludoteca.pdf",
            "title": "Il gioco astratto Quoridor è incredibilmente",
            "content": ITALIAN_TEXT + " Sagrada, Azul, Quoridor, Catan",
            "snippet": "",
        }, {
            "url": "https://www.example.it/uploads/regole.pdf",
            "title": "Sagrada - regolamento",
            "content": ITALIAN_TEXT,
            "snippet": "",
        }]},
        {},
    )
    candidates = provider_with(web).discover(QUERY)
    assert [item.url for item in candidates] == ["https://www.example.it/uploads/regole.pdf"]


def test_spanish_text_is_not_italian() -> None:
    spanish = (
        "El juego se desarrolla en turnos. Cada jugador roba una carta y luego debe elegir una de las "
        "acciones del tablero. Cuando el mazo se acaba la partida termina y el jugador con más puntos gana. "
        "Para preparar el juego, mezclad las cartas y repartid cinco cartas a cada jugador. Los jugadores "
        "que no pueden jugar pasan el turno por la izquierda."
    )
    assert text_language(spanish) == "es"


def test_browser_fallback_drops_content_encoding() -> None:
    import httpx

    from boardgamecompanion.rulebook_providers import ProviderHttpClient

    class Transport(httpx.BaseTransport):
        def handle_request(self, request):
            return httpx.Response(429 if "products" in str(request.url) else 200, content=b"ok")

    def browser(url):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<h1>Sagrada</h1>")

    client = ProviderHttpClient(
        client=httpx.Client(transport=Transport()), browser_fallback_hosts={"craniocreations.it"},
        browser_fetch=browser, min_interval_seconds=0,
    )
    response = client.get("https://craniocreations.it/products/sagrada", allowed_hosts={"craniocreations.it"})
    assert response.status_code == 200 and b"Sagrada" in response.content


def test_side_material_is_not_the_rulebook() -> None:
    from boardgamecompanion.italian_rulebook_search import side_material

    assert side_material("https://x.ru/Kingdomino_Expansion_Print_Play_The_Court.pdf", ["kingdomino"])
    assert side_material("https://x.it/Sagrada_FAQ_ITA.pdf", ["sagrada"])
    assert not side_material("https://x.it/Sagrada_ITA_Rules.pdf", ["sagrada"])
    # the game itself is an expansion: its own name is not a reason to drop it
    assert not side_material("https://x.it/Sagrada_Expansion_regole.pdf", ["sagrada 5 6 player expansion"])
