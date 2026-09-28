from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

import httpx
import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.rulebook_discovery import RulebookDiscoveryService
from boardgamecompanion.rulebook_providers import (
    AsmodeeItaliaProvider,
    MsEdizioniProvider,
    PendragonItaliaProvider,
    ProviderHttpClient,
    ReposProductionProvider,
    production_rulebook_providers,
)
from boardgamecompanion.rulebook_review import RulebookReviewQueue
from boardgamecompanion.rulebook_fetch import RulebookFetchResult
from boardgamecompanion.rulebook_updates import RulebookUpdateService
from boardgamecompanion.rulebooks import (
    RulebookCandidate,
    RulebookProviderError,
    RulebookQuery,
    RulebookResolver,
)


def query(**overrides) -> RulebookQuery:
    values = {
        "bgg_id": 173346,
        "title": "7 Wonders Duel",
        "original_title": "7 Wonders Duel",
        "year": 2015,
        "item_type": "boardgame",
        "publishers": ("Repos Production",),
        "verified_publishers": ("Repos Production",),
        "verified_titles": ("7 Wonders Duel",),
        "bgg_identity_verified": True,
    }
    values.update(overrides)
    return RulebookQuery(**values)


def repos_html(title: str = "7 Wonders Duel") -> bytes:
    return f"""<!doctype html><h1>{title}</h1>
      <a href='https://cdn.svc.asmodee.net/games/7wd/it/7wd-rules-it.pdf'>IT</a>
      <a href='https://cdn.svc.asmodee.net/games/7wd/en/7wd-rules-us.pdf'>EN</a>
      <a href='https://cdn.svc.asmodee.net/games/7wd/fr/7wd-rules-fr.pdf'>FR</a>""".encode()


def test_repos_adapter_normalizes_both_it_and_en_and_filters_other_languages() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=repos_html(), request=request))
    provider = ReposProductionProvider(
        ProviderHttpClient(client=httpx.Client(transport=transport), min_interval_seconds=0)
    )

    candidates = tuple(provider.discover(query()))

    assert [item.language for item in candidates] == ["it", "en"]
    assert all(item.bgg_id == 173346 for item in candidates)
    assert all(item.source_kind.value == "official_publisher" for item in candidates)
    assert all(item.confidence == 100 and item.official for item in candidates)


def test_repos_adapter_requires_publisher_and_exact_base_expansion_identity() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=repos_html("7 Wonders Duel: Pantheon"), request=request)

    provider = ReposProductionProvider(
        ProviderHttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval_seconds=0)
    )
    assert tuple(provider.discover(query(publishers=("Other",)))) == ()
    assert calls == 0
    assert tuple(provider.discover(query())) == ()
    assert calls == 1


def test_repos_nested_pantheon_expansion_finds_official_it_rules_with_exact_identity() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/en/games/7-wonders-duel-pantheon":
            return httpx.Response(404, request=request)
        if request.url.path == "/en/games/7-wonders-duel/pantheon":
            return httpx.Response(
                200,
                content=b"""<!doctype html><h1>Pantheon</h1>
                  <a href="https://cdn.svc.asmodee.net/production-rprod/storage/downloads/games/7wonders-duel-pantheon/it/7dpa-rules-it-16245352255fvc2.pdf">IT</a>
                  <a href="https://cdn.svc.asmodee.net/production-rprod/storage/downloads/games/7wonders-duel-pantheon/en/7dpa-rules-en.pdf">GB</a>""",
                request=request,
            )
        return httpx.Response(404, request=request)

    provider = ReposProductionProvider(
        ProviderHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval_seconds=0,
        )
    )
    pantheon = query(
        bgg_id=202976,
        title="7 Wonders Duel: Pantheon",
        original_title="7 Wonders Duel: Pantheon",
        item_type="boardgameexpansion",
        verified_titles=("7 Wonders Duel: Pantheon",),
    )
    candidates = tuple(provider.discover(pantheon))
    assert [c.language for c in candidates] == ["it", "en"]
    assert [c.bgg_id for c in candidates] == [202976, 202976]
    assert all(c.game_title == "7 Wonders Duel: Pantheon" for c in candidates)
    assert all(
        tuple(c.metadata["identity_evidence"])
        == (
            "official_nested_expansion_path_and_heading",
            "bgg_api_exact_id_title_publisher_crosscheck",
        )
        for c in candidates
    )
    assert requested == [
        "https://www.rprod.com/en/games/7-wonders-duel-pantheon",
        "https://www.rprod.com/en/games/7-wonders-duel/pantheon",
    ]


def test_repos_nested_expansion_rejects_wrong_heading_and_never_guesses_base_path() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/pantheon"):
            return httpx.Response(
                200, content=repos_html("Agora"), request=request
            )
        return httpx.Response(404, request=request)

    provider = ReposProductionProvider(
        ProviderHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval_seconds=0,
        )
    )
    pantheon = query(
        bgg_id=202976,
        title="7 Wonders Duel: Pantheon",
        item_type="boardgameexpansion",
        verified_titles=("7 Wonders Duel: Pantheon",),
    )
    assert tuple(provider.discover(pantheon)) == ()
    assert "/en/games/7-wonders-duel/pantheon" in requests
    requests.clear()
    assert tuple(provider.discover(pantheon.__class__(
        bgg_id=202976, title="7 Wonders Duel: Pantheon",
        item_type="boardgame", publishers=("Repos Production",),
        verified_publishers=("Repos Production",),
        verified_titles=("7 Wonders Duel: Pantheon",),
        bgg_identity_verified=True,
    ))) == ()
    assert "/en/games/7-wonders-duel/pantheon" not in requests


def test_repos_nested_expansion_preserves_manual_review_without_verified_bgg_identity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pantheon"):
            return httpx.Response(
                200,
                content=b"""<h1>Pantheon</h1>
                <a href="https://cdn.svc.asmodee.net/rules/pantheon/it/rules-it.pdf">IT</a>""",
                request=request,
            )
        return httpx.Response(404, request=request)

    provider = ReposProductionProvider(
        ProviderHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval_seconds=0,
        )
    )
    title_only = query(
        bgg_id=202976,
        title="7 Wonders Duel: Pantheon",
        item_type="boardgameexpansion",
        verified_titles=(),
        verified_publishers=(),
        bgg_identity_verified=False,
    )
    candidates = tuple(provider.discover(title_only))
    assert len(candidates) == 1
    assert candidates[0].bgg_id is None
    assert candidates[0].official is True
    assert tuple(candidates[0].metadata["identity_evidence"]) == (
        "official_nested_expansion_path_and_heading",
        "catalog_publisher_compatible",
    )


def test_official_adapter_does_not_self_attest_bgg_identity_without_api_crosscheck() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=repos_html(), request=request))
    provider = ReposProductionProvider(
        ProviderHttpClient(client=httpx.Client(transport=transport), min_interval_seconds=0)
    )
    unverified = query(verified_publishers=(), bgg_identity_verified=False)
    candidates = tuple(provider.discover(unverified))
    assert candidates and all(item.bgg_id is None for item in candidates)
    assert all(item.confidence == 100 for item in candidates)

    wrong_title = query(verified_titles=("Different BGG Game",))
    candidates = tuple(provider.discover(wrong_title))
    assert candidates and all(item.bgg_id is None for item in candidates)


def test_publisher_compatibility_does_not_use_substring_matches() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=repos_html(), request=request)

    provider = ReposProductionProvider(
        ProviderHttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval_seconds=0)
    )
    assert tuple(provider.discover(query(publishers=("Not Repos Production Holdings",)))) == ()
    assert calls == 0


def test_provider_http_client_uses_browser_compatible_public_headers() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=b"ok", request=request)

    client = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        min_interval_seconds=0,
    )
    client.get("https://provider.example/index", allowed_hosts={"provider.example"})

    assert captured[0].headers["user-agent"].startswith("Mozilla/5.0")
    assert captured[0].headers["accept-language"].startswith("it-IT")
    assert captured[0].headers["accept-encoding"] == "identity"


def test_http_client_uses_browser_fallback_only_after_403_on_allowed_host() -> None:
    primary_calls: list[str] = []
    browser_calls: list[str] = []

    def primary(request: httpx.Request) -> httpx.Response:
        primary_calls.append(str(request.url))
        return httpx.Response(403, content=b"blocked", request=request)

    def browser(url: str) -> httpx.Response:
        browser_calls.append(url)
        return httpx.Response(
            200,
            content=b"official page",
            headers={"content-type": "text/html"},
            request=httpx.Request("GET", url),
        )

    client = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(primary)),
        min_interval_seconds=0,
        browser_fallback_hosts={"provider.example"},
        browser_fetch=browser,
    )
    response = client.get(
        "https://provider.example/index",
        allowed_hosts={"provider.example"},
    )

    assert response.content == b"official page"
    assert primary_calls == ["https://provider.example/index"]
    assert browser_calls == ["https://provider.example/index"]


def test_http_client_never_uses_browser_fallback_for_unlisted_host() -> None:
    browser_calls: list[str] = []

    def primary(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"blocked", request=request)

    def browser(url: str) -> httpx.Response:
        browser_calls.append(url)
        return httpx.Response(200, content=b"unexpected", request=httpx.Request("GET", url))

    client = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(primary)),
        min_interval_seconds=0,
        browser_fallback_hosts={"official.example"},
        browser_fetch=browser,
    )
    with pytest.raises(RulebookProviderError, match="HTTP 403"):
        client.get(
            "https://community.example/index",
            allowed_hosts={"community.example"},
        )

    assert browser_calls == []


def test_browser_fallback_redirect_stays_inside_provider_origin_allowlist() -> None:
    def primary(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"blocked", request=request)

    def browser(url: str) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://internal.invalid/private"},
            request=httpx.Request("GET", url),
        )

    client = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(primary)),
        min_interval_seconds=0,
        browser_fallback_hosts={"provider.example"},
        browser_fetch=browser,
    )
    with pytest.raises(RulebookProviderError, match="escaped the provider origin"):
        client.get(
            "https://provider.example/index",
            allowed_hosts={"provider.example"},
        )


def test_production_provider_factory_limits_browser_fallback_to_official_hosts() -> None:
    providers = {
        item.name: item
        for item in production_rulebook_providers(min_interval_seconds=0)
    }
    repos = providers["repos_production"]
    asmodee = providers["asmodee_italia"]
    pendragon = providers["pendragon_italia"]
    ms_edizioni = providers["ms_edizioni"]
    community = providers["rulebook_org"]
    generic = [
        value for name, value in providers.items()
        if name.startswith("official_site_")
    ]
    assert len(generic) == 5
    assert all(item.http.browser_fallback_hosts == frozenset() for item in generic)

    assert repos.http.browser_fallback_hosts == {"www.rprod.com", "rprod.com"}
    assert asmodee.http.browser_fallback_hosts == {
        "www.asmodee.it",
        "asmodee.it",
        "www.rprod.com",
        "rprod.com",
    }
    assert pendragon.http.browser_fallback_hosts == {
        "pendragongamestudio.com",
        "www.pendragongamestudio.com",
    }
    assert ms_edizioni.http.browser_fallback_hosts == {
        "www.msedizioni.it",
        "msedizioni.it",
    }
    assert community.http.browser_fallback_hosts == frozenset()


def test_pendragon_matches_verified_italian_alias_for_expansion() -> None:
    html = b"""<!doctype html>
      <h2>Last Aurora regole IT</h2>
      <a href='/it/?ddownload=base'>Download</a>
      <h2>Last Aurora Acciaio Siderale regole IT</h2>
      <a href='/it/?ddownload=frozen'>Download</a>
    """

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=html, request=request)
    )
    provider = PendragonItaliaProvider(
        ProviderHttpClient(
            client=httpx.Client(transport=transport),
            min_interval_seconds=0,
        )
    )
    candidate_query = query(
        bgg_id=334710,
        title="Last Aurora: Frozen Steel",
        original_title="Last Aurora: Frozen Steel",
        item_type="boardgameexpansion",
        publishers=("Pendragon Game Studio",),
        verified_publishers=("Pendragon Game Studio",),
        verified_titles=(
            "Last Aurora: Frozen Steel",
            "Last Aurora: Acciaio Siderale",
        ),
    )

    candidates = tuple(provider.discover(candidate_query))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.language == "it"
    assert candidate.bgg_id == 334710
    assert candidate.official is True
    assert candidate.confidence == 100
    assert candidate.source_kind.value == "official_localizer"
    assert candidate.url.endswith("?ddownload=frozen")


def test_pendragon_refuses_unverified_localized_title() -> None:
    html = b"""<!doctype html>
      <h2>Different Game regole IT</h2>
      <a href='/it/?ddownload=wrong'>Download</a>
    """
    provider = PendragonItaliaProvider(
        ProviderHttpClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=html, request=request)
                )
            ),
            min_interval_seconds=0,
        )
    )
    candidate_query = query(
        bgg_id=334710,
        title="Last Aurora: Frozen Steel",
        publishers=("Pendragon Game Studio",),
        verified_publishers=("Pendragon Game Studio",),
        verified_titles=("Last Aurora: Frozen Steel",),
    )

    assert tuple(provider.discover(candidate_query)) == ()


def test_ms_edizioni_requires_exact_bgg_link_before_trusting_manual() -> None:
    search_html = b"""<!doctype html>
      <a href='https://www.msedizioni.it/prodotto/navoria/'>Navoria</a>
      <a href='https://www.msedizioni.it/prodotto/not-navoria/'>Not Navoria</a>
    """
    product_html = b"""<!doctype html>
      <h1>Navoria</h1>
      <a href='https://www.msedizioni.it/wp-content/uploads/PDF-gdt/Navoria-MSEdizioni.pdf'>
        Scarica il Regolamento
      </a>
      <a href='https://boardgamegeek.com/boardgame/371932/explorers-of-navoria'>
        Il gioco su Boardgamegeek
      </a>
    """
    wrong_html = product_html.replace(b"/371932/", b"/999999/")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/":
            return httpx.Response(200, content=search_html, request=request)
        if path == "/prodotto/navoria/":
            return httpx.Response(200, content=product_html, request=request)
        if path == "/prodotto/not-navoria/":
            return httpx.Response(200, content=wrong_html, request=request)
        return httpx.Response(404, request=request)

    provider = MsEdizioniProvider(
        ProviderHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval_seconds=0,
        )
    )
    candidate_query = query(
        bgg_id=371932,
        title="Explorers of Navoria",
        original_title="Navoria",
        publishers=("MS Edizioni",),
        verified_publishers=("MS Edizioni",),
        verified_titles=("Explorers of Navoria", "Navoria"),
    )

    candidates = tuple(provider.discover(candidate_query))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.bgg_id == 371932
    assert candidate.language == "it"
    assert candidate.official is True
    assert candidate.confidence == 100
    assert candidate.url == (
        "https://www.msedizioni.it/wp-content/uploads/PDF-gdt/"
        "Navoria-MSEdizioni.pdf"
    )
    assert "official_page_exact_bgg_link" in candidate.metadata["identity_evidence"]


def test_ms_edizioni_converts_publisher_linked_dropbox_rulebook_to_download() -> None:
    search_html = b"""<!doctype html>
      <a href='/prodotto/food-chain-magnate-ketchup-e-altre-idee/'>
        Food Chain Magnate - Ketchup e altre idee
      </a>
    """
    product_html = b"""<!doctype html>
      <h1>Ketchup e altre idee</h1>
      <a href='https://www.dropbox.com/scl/fi/file/manual.pdf?dl=0&rlkey=trusted'>
        Scarica il regolamento in italiano
      </a>
      <a href='https://boardgamegeek.com/boardgame/261526/food-chain-magnate-ketchup'>
        Il gioco su Boardgamegeek
      </a>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, content=search_html, request=request)
        if request.url.path.startswith("/prodotto/"):
            return httpx.Response(200, content=product_html, request=request)
        return httpx.Response(404, request=request)

    provider = MsEdizioniProvider(
        ProviderHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval_seconds=0,
        )
    )
    candidate_query = query(
        bgg_id=261526,
        title="Food Chain Magnate: The Ketchup Mechanism & Other Ideas",
        item_type="boardgameexpansion",
        publishers=("MS Edizioni",),
        verified_publishers=("MS Edizioni",),
        verified_titles=(
            "Food Chain Magnate: The Ketchup Mechanism & Other Ideas",
            "Food Chain Magnate: Ketchup e altre idee",
        ),
    )

    candidates = tuple(provider.discover(candidate_query))

    assert len(candidates) == 1
    assert candidates[0].url.startswith("https://www.dropbox.com/")
    assert "dl=1" in candidates[0].url
    assert "rlkey=trusted" in candidates[0].url


def test_asmodee_follows_trusted_official_rulebook_page_and_keeps_bgg_identity() -> None:
    asmodee_html = b"""<!doctype html><h1>7 Wonders Duel</h1>
      <a href='https://www.rprod.com/it/games/7-wonders-duel'>Scarica il regolamento</a>"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.asmodee.it":
            return httpx.Response(200, content=asmodee_html, request=request)
        if request.url.host == "www.rprod.com":
            return httpx.Response(200, content=repos_html(), request=request)
        return httpx.Response(404, request=request)

    provider = AsmodeeItaliaProvider(
        ProviderHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval_seconds=0,
        )
    )
    candidates = tuple(provider.discover(query()))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.language == "it"
    assert candidate.bgg_id == 173346
    assert candidate.confidence == 100
    assert candidate.source_kind.value == "official_localizer"
    assert candidate.metadata["rulebook_page"] == (
        "https://www.rprod.com/it/games/7-wonders-duel"
    )


class StaticProvider:
    def __init__(self, name: str, values: tuple[RulebookCandidate, ...] = (), error: Exception | None = None):
        self.name = name
        self.values = values
        self.error = error

    def discover(self, _: RulebookQuery):
        if self.error:
            raise self.error
        return self.values


def candidate(*, provider: str, source: str, language: str, url: str, official: bool, confidence: int, bgg_id: int | None = 173346) -> RulebookCandidate:
    return RulebookCandidate(
        provider=provider,
        source_kind=source,
        url=url,
        language=language,
        official=official,
        confidence=confidence,
        bgg_id=bgg_id,
        game_title="7 Wonders Duel",
        year=2015,
    )


def test_ranking_keeps_trust_authoritative_then_prefers_it_over_en() -> None:
    official_en = candidate(provider="official", source="official_publisher", language="en", url="https://publisher.example/en.pdf", official=True, confidence=100)
    official_it = candidate(provider="official", source="official_publisher", language="it", url="https://publisher.example/it.pdf", official=True, confidence=100)
    community_it = candidate(provider="community", source="community", language="it", url="https://community.example/it.pdf", official=False, confidence=70, bgg_id=None)
    result = RulebookResolver((StaticProvider("all", (community_it, official_en, official_it)),)).resolve(query())
    assert [item.candidate for item in result.candidates] == [official_it, official_en, community_it]


def test_conflicting_bgg_id_is_rejected_and_duplicate_url_is_deduplicated() -> None:
    good = candidate(provider="a", source="official_publisher", language="it", url="https://publisher.example/rules.pdf", official=True, confidence=100)
    duplicate = candidate(provider="b", source="official_mirror", language="it", url="https://publisher.example/rules.pdf#copy", official=True, confidence=95)
    conflict = candidate(provider="bad", source="official_publisher", language="it", url="https://publisher.example/wrong.pdf", official=True, confidence=100, bgg_id=99)
    result = RulebookResolver((StaticProvider("values", (good, duplicate, conflict)),)).resolve(query())
    assert [item.candidate for item in result.candidates] == [good]


def test_provider_failure_is_isolated_from_partial_success() -> None:
    good = candidate(provider="good", source="official_publisher", language="it", url="https://publisher.example/rules.pdf", official=True, confidence=100)
    result = RulebookResolver((StaticProvider("broken", error=RulebookProviderError("down")), StaticProvider("good", (good,)))).resolve(query())
    assert result.best and result.best.candidate == good
    assert [(item.provider, item.error_type) for item in result.failures] == [("broken", "RulebookProviderError")]


def test_http_client_bounds_timeout_retries_and_rate_limit() -> None:
    calls = 0
    sleeps: list[float] = []
    ticks = iter((0.0, 0.0, 0.1, 0.1, 2.0, 2.0))

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, content=b"ok", request=request)

    client = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=2,
        min_interval_seconds=1,
        sleep=sleeps.append,
        monotonic=lambda: next(ticks),
    )
    response = client.get("https://provider.example/index", allowed_hosts={"provider.example"})
    assert response.content == b"ok"
    assert calls == 2
    assert sleeps == [0.25, 0.9]


def test_http_client_refuses_https_downgrade_and_streams_byte_limit() -> None:
    downgrade = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": "http://provider.example/index"}, request=request)
        )),
        min_interval_seconds=0,
    )
    with pytest.raises(RulebookProviderError, match="HTTPS"):
        downgrade.get("https://provider.example/index", allowed_hosts={"provider.example"})

    oversized = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"123456", request=request)
        )),
        max_response_bytes=5,
        min_interval_seconds=0,
    )
    with pytest.raises(RulebookProviderError, match="byte limit"):
        oversized.get("https://provider.example/index", allowed_hosts={"provider.example"})

    encoded = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-encoding": "gzip"},
                stream=httpx.ByteStream(b"compressed"),
                request=request,
            )
        )),
        min_interval_seconds=0,
    )
    with pytest.raises(RulebookProviderError, match="encoding"):
        encoded.get("https://provider.example/index", allowed_hosts={"provider.example"})


def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    now = datetime.now(UTC).isoformat()
    with db.transaction() as connection:
        connection.execute(
            """INSERT INTO board_games
               (bgg_id,title,original_title,year_published,item_type,source_metadata_json,created_at,updated_at)
               VALUES (173346,'7 Wonders Duel','7 Wonders Duel',2015,'boardgame','{}',?,?)""",
            (now, now),
        )
        game_id = connection.execute("SELECT id FROM board_games WHERE bgg_id=173346").fetchone()["id"]
        connection.execute(
            """INSERT INTO collection_entries
               (board_game_id,own,version_publishers,source_metadata_json,created_at,updated_at)
               VALUES (?,1,'Repos Production','{}',?,?)""", (game_id, now, now)
        )
    return db


def test_discovery_query_keeps_edition_publisher_separate_from_bgg_evidence(tmp_path: Path) -> None:
    db = database(tmp_path)
    service = RulebookDiscoveryService(db, ())
    candidate_query = service._query(173346)
    assert candidate_query.edition_publishers == ("Repos Production",)
    assert candidate_query.publishers == ("Repos Production",)
    assert candidate_query.verified_publishers == ()
    assert candidate_query.bgg_identity_verified is False


def discovery_providers() -> tuple[StaticProvider, ...]:
    return (
        StaticProvider("official", (
            candidate(provider="official", source="official_publisher", language="it", url="https://publisher.example/it.pdf", official=True, confidence=100),
            candidate(provider="official", source="official_publisher", language="en", url="https://publisher.example/en.pdf", official=True, confidence=100),
        )),
        StaticProvider("community", (
            candidate(provider="community", source="community", language="it", url="https://community.example/it.pdf", official=False, confidence=70, bgg_id=None),
        )),
    )


def test_discovery_routes_candidates_through_policy_and_rediscovery_is_idempotent(tmp_path: Path) -> None:
    db = database(tmp_path)
    service = RulebookDiscoveryService(db, discovery_providers(), refresh_seconds=3600, empty_refresh_seconds=3600)
    assert service.synchronize_catalog() == 1

    first = service.run_game(173346)
    second = service.run_game(173346)
    reviews = RulebookReviewQueue(db).list(limit=20)

    assert first["candidates_found"] == 3 and first["review_items_created"] == 3
    assert second["candidates_found"] == 3 and second["review_items_created"] == 0
    assert first["generation"] == 1
    assert second["generation"] == 2
    assert len(first["review_items"]) == 3
    assert {item["id"] for item in first["review_items"]} == {
        item["id"] for item in second["review_items"]
    }
    assert all(item["created"] for item in first["review_items"])
    assert not any(item["created"] for item in second["review_items"])
    assert {
        (
            item["candidate"]["provider"],
            item["candidate"]["url"],
            item["candidate"]["language"],
        )
        for item in first["review_items"]
    } == {
        ("official", "https://publisher.example/it.pdf", "it"),
        ("official", "https://publisher.example/en.pdf", "en"),
        ("community", "https://community.example/it.pdf", "it"),
    }
    assert all(
        set(item["candidate"])
        == {
            "provider",
            "source_kind",
            "url",
            "language",
            "document_type",
            "official",
            "confidence",
            "bgg_id",
        }
        for item in first["review_items"]
    )
    assert reviews["total"] == 3
    assert sorted(item["status"] for item in reviews["items"]) == ["approved", "approved", "pending"]
    community = next(item for item in reviews["items"] if item["candidate"]["provider"] == "community")
    assert community["candidate"]["official"] is False
    assert community["policy_action"] == "review"


def test_discovery_status_read_does_not_resynchronize_catalog(tmp_path: Path) -> None:
    db = database(tmp_path)
    service = RulebookDiscoveryService(db, discovery_providers())
    assert service.synchronize_catalog() == 1

    def unexpected_sync(*args, **kwargs):
        raise AssertionError("status read attempted a catalog write")

    service.synchronize_catalog = unexpected_sync  # type: ignore[method-assign]
    status = service.list_status(bgg_id=173346)

    assert status["count"] == 1
    assert status["items"][0]["bgg_id"] == 173346


def test_discovery_persists_state_across_service_restart_and_partial_outage(tmp_path: Path) -> None:
    db = database(tmp_path)
    providers = (StaticProvider("broken", error=RuntimeError("offline")), discovery_providers()[0])
    first = RulebookDiscoveryService(db, providers)
    first.synchronize_catalog()
    result = first.run_game(173346)
    restarted = RulebookDiscoveryService(db, providers)
    state = restarted.list_status(bgg_id=173346)["items"][0]

    assert result["status"] == "partial"
    assert result["provider_results"] == [
        {
            "provider": "broken",
            "outcome": "failed",
            "candidate_count": 0,
            "error_type": "RuntimeError",
            "error_message": "offline",
        },
        {
            "provider": "official",
            "outcome": "succeeded",
            "candidate_count": 2,
            "error_type": None,
            "error_message": None,
        },
    ]
    assert state["status"] == "partial"
    assert state["provider_failures"] == 1
    with db.connect() as connection:
        runs = connection.execute("SELECT provider,outcome FROM rulebook_discovery_provider_runs ORDER BY provider").fetchall()
    assert [(row["provider"], row["outcome"]) for row in runs] == [("broken", "failed"), ("official", "succeeded")]


def test_discovery_to_policy_guarded_fetch_archive_and_auto_index_queue(tmp_path: Path) -> None:
    db = database(tmp_path)
    discovery = RulebookDiscoveryService(db, (discovery_providers()[0],))
    discovery.synchronize_catalog()
    result = discovery.run_game(173346)
    assert result["review_items_created"] == 2

    pdf = b"%PDF-1.4\nreal pipeline fixture\n%%EOF\n"

    class Fetcher:
        def fetch(self, found: RulebookCandidate) -> RulebookFetchResult:
            digest = hashlib.sha256(pdf).hexdigest()
            path = tmp_path / "manuals" / f"{digest}.pdf"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pdf)
            return RulebookFetchResult(
                candidate=found,
                requested_url=found.url,
                final_url=found.url,
                status_code=200,
                content_type="application/pdf",
                byte_size=len(pdf),
                sha256=digest,
                local_path=str(path),
            )

    updates = RulebookUpdateService(
        db,
        tmp_path / "manuals",
        fetcher_factory=Fetcher,
        default_interval_seconds=3600,
        retry_base_seconds=60,
        retry_max_seconds=60,
        lease_seconds=60,
    )
    synchronized = updates.synchronize_approved_targets()
    assert synchronized["created"] == 2
    review = RulebookReviewQueue(db).list(status="approved", limit=10)["items"][0]
    archived = updates.run_review_now(review["id"])

    assert archived["outcome"] == "created"
    with db.connect() as connection:
        document = connection.execute("SELECT id,language,source_provider,is_official FROM game_documents").fetchone()
        job = connection.execute("SELECT status,stage FROM document_index_jobs WHERE document_id=?", (document["id"],)).fetchone()
    assert document["source_provider"] == "official"
    assert document["is_official"] == 1
    assert job["status"] == "pending" and job["stage"] == "queued"
