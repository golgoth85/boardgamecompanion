from __future__ import annotations

import httpx
import pytest

from boardgamecompanion.official_site_discovery import (
    PublisherSite,
    PublisherSiteProvider,
    PublisherSiteResolver,
    VERIFIED_PUBLISHER_SITES,
)
from boardgamecompanion.rulebook_providers import ProviderHttpClient
from boardgamecompanion.rulebooks import RulebookQuery, RulebookResolver


def case(**overrides) -> RulebookQuery:
    values = {
        "bgg_id": 334710,
        "title": "Last Aurora: Frozen Steel",
        "original_title": "Last Aurora: Acciaio Siderale",
        "verified_titles": (
            "Last Aurora: Frozen Steel",
            "Last Aurora: Acciaio Siderale",
        ),
        "publishers": ("Pendragon Game Studio",),
        "verified_publishers": ("Pendragon Game Studio",),
        "edition_publishers": ("Pendragon Game Studio",),
        "bgg_identity_verified": True,
        "item_type": "boardgameexpansion",
    }
    values.update(overrides)
    return RulebookQuery(**values)


def provider(site: PublisherSite, handler):
    return PublisherSiteProvider(
        site,
        ProviderHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval_seconds=0,
            max_attempts=1,
            user_agent="BoardGameCompanion/0.2 (official-rulebook-discovery)",
        ),
    )


def site(key):
    return next(item for item in VERIFIED_PUBLISHER_SITES if item.key == key)


def test_resolver_prefers_edition_localizer_then_verified_bgg_publisher():
    q = case(
        publishers=("MS Edizioni", "Pendragon Game Studio"),
        verified_publishers=("Pendragon Game Studio",),
        edition_publishers=("MS Edizioni",),
    )
    assert [item.key for item in PublisherSiteResolver().resolve(q)] == [
        "ms_edizioni",
        "pendragon_italia",
    ]


def test_unknown_publisher_never_results_in_a_guessed_domain():
    accessed = []

    def unexpected(req):
        accessed.append(str(req.url))
        raise AssertionError("No network request for unverified publisher")

    q = case(
        publishers=("Similar Publisher GmbH",),
        verified_publishers=(),
        edition_publishers=("Similar Publisher GmbH",),
    )
    assert PublisherSiteResolver().resolve(q) == ()
    for directory_site in VERIFIED_PUBLISHER_SITES:
        assert provider(directory_site, unexpected).discover(q) == ()
    assert accessed == []


def test_pendragon_catalog_finds_italian_expansion_without_confusing_base():
    accessed = []

    def handler(req):
        accessed.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        if req.url.path == "/it/download/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"""<h2>Last Aurora regole IT</h2>
                  <a href='/it/?ddownload=base'>Download</a>
                  <h2>Last Aurora Acciaio Siderale regole IT</h2>
                  <a href='/it/?ddownload=frozen'>Download</a>
                  <h2>Last Aurora Extra rules IT</h2>
                  <a href='/it/?ddownload=extras'>Download</a>""",
                request=req,
            )
        return httpx.Response(404, request=req)

    result = provider(site("pendragon_italia"), handler).discover(case())
    assert len(result) == 1
    assert result[0].url == "https://pendragongamestudio.com/it/?ddownload=frozen"
    assert result[0].language == "it"
    assert result[0].confidence == 100
    assert result[0].bgg_id == 334710
    assert "official_download_catalog_title_exact" in result[0].metadata[
        "identity_evidence"
    ]
    assert not any("ddownload=frozen" in url for url in accessed)


def test_ms_edizioni_search_uses_product_page_and_exact_bgg_proof():
    visited = []

    def handler(req):
        visited.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        if req.url.path == "/" and "s" in req.url.params:
            return httpx.Response(
                200, headers={"content-type": "text/html"},
                content=b"""<h1>Search results</h1>
                  <a href='/prodotto/navoria/'>Navoria</a>
                  <a href='/prodotto/navoria-expansion/'>Navoria: Expansion</a>""",
                request=req,
            )
        if req.url.path == "/prodotto/navoria/":
            return httpx.Response(
                200, headers={"content-type": "text/html"},
                content=b"""<h1>Navoria</h1>
                <a href='https://boardgamegeek.com/boardgame/371932/explorers-of-navoria'>BGG</a>
                <a href='https://www.msedizioni.it/wp-content/uploads/navoria-regolamento-IT.pdf'>Scarica il regolamento in italiano</a>""",
                request=req,
            )
        if req.url.path == "/prodotto/navoria-expansion/":
            return httpx.Response(
                200, headers={"content-type": "text/html"},
                content=b"""<h1>Navoria: Expansion</h1>
                <a href='https://boardgamegeek.com/boardgameexpansion/88888'>BGG</a>
                <a href='https://www.msedizioni.it/files/expansion-regolamento-IT.pdf'>Scarica il regolamento italiano</a>""",
                request=req,
            )
        return httpx.Response(404, request=req)

    q = case(
        bgg_id=371932,
        title="Explorers of Navoria",
        original_title="Navoria",
        verified_titles=("Explorers of Navoria", "Navoria"),
        publishers=("MS Edizioni",),
        verified_publishers=(),
        edition_publishers=("MS Edizioni",),
        item_type="boardgame",
    )
    result = provider(site("ms_edizioni"), handler).discover(q)
    assert len(result) == 1
    assert result[0].bgg_id == 371932
    assert result[0].confidence == 100
    assert result[0].language == "it"
    assert "msedizioni.it" in result[0].url
    assert any("post_type=product" in path for path in visited)


def test_mismatched_expansion_or_multiple_bgg_ids_not_unattended():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"""<h1>Last Aurora: Frozen Steel</h1>
            <a href='https://boardgamegeek.com/boardgame/334710'>Expansion</a>
            <a href='https://boardgamegeek.com/boardgame/274450'>Base game</a>
            <a href='/it/rules-it.pdf'>Scarica il regolamento in italiano</a>""",
            request=req,
        )
    result = provider(site("pendragon_italia"), handler).discover(case(
        verified_publishers=(), edition_publishers=("Pendragon Game Studio",)
    ))
    assert result
    assert all(item.confidence == 90 and item.bgg_id is None for item in result)


def test_italian_storefront_not_it_language_proof_by_itself():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"""<h1>Navoria</h1>
            <a href='https://boardgamegeek.com/boardgame/371932'>BGG</a>
            <a href='https://www.msedizioni.it/files/rules.pdf'>Scarica il regolamento</a>""",
            request=req,
        )
    q = case(
        bgg_id=371932, title="Navoria", original_title=None,
        verified_titles=("Navoria",), publishers=("MS Edizioni",),
        verified_publishers=("MS Edizioni",), edition_publishers=("MS Edizioni",),
        item_type="boardgame",
    )
    result = provider(site("ms_edizioni"), handler).discover(q)
    assert result
    assert result[0].language == "it"
    assert result[0].bgg_id is None
    assert result[0].confidence == 90


def test_external_website_and_unapproved_download_host_are_rejected():
    evil = "https://127.0.0.1/private.pdf"

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=(
                "<h1>Last Aurora: Frozen Steel</h1>"
                f"<a href='{evil}'>Scarica il regolamento italiano</a>"
                "<a href='https://evil.example/rules-it.pdf'>Download rules IT</a>"
                "<a href='/it/rules-it.pdf'>Scarica il regolamento italiano</a>"
            ).encode(), request=req,
        )

    result = provider(site("pendragon_italia"), handler).discover(case())
    assert len(result) == 1
    assert result[0].url.startswith("https://pendragongamestudio.com/")


def test_robots_disallow_prevents_fetch_even_on_known_official_site():
    visited = []

    def handler(req):
        visited.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(
                200, headers={"content-type": "text/plain"},
                content=b"User-agent: *\nDisallow: /it/download/\nDisallow: /it/product/\nDisallow: /it/?s=\n",
                request=req,
            )
        return httpx.Response(200, content=b"<h1>Last Aurora</h1>", request=req)

    q = case(
        bgg_id=274450, title="Last Aurora", original_title="Last Aurora",
        verified_titles=("Last Aurora",),
        item_type="boardgame",
    )
    result = provider(site("pendragon_italia"), handler).discover(q)
    assert result == ()
    assert all("/it/download/" not in url for url in visited)
    assert all("/it/product/" not in url for url in visited)


def test_csv_only_catalog_candidate_requires_review_not_unattended():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"""<h1>Last Aurora</h1>
            <a href='/it/last-aurora-regolamento-IT.pdf'>Scarica il regolamento italiano</a>""",
            request=req,
        )
    q = case(
        bgg_id=274450, title="Last Aurora", original_title="Last Aurora",
        verified_titles=(), verified_publishers=(),
        bgg_identity_verified=False, item_type="boardgame",
    )
    result = provider(site("pendragon_italia"), handler).discover(q)
    assert result
    assert all(item.confidence == 90 and item.bgg_id is None for item in result)


def test_it_precedes_en_in_generic_site_resolution():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"""<h1>Last Aurora: Frozen Steel</h1>
              <a href='/it/frozen-rules-it.pdf'>Rules IT</a>
              <a href='/en/frozen-rules-en.pdf'>Rules EN</a>""",
            request=req,
        )
    generic = provider(site("pendragon_italia"), handler)
    result = RulebookResolver((generic,)).resolve(case())
    assert [item.candidate.language for item in result.candidates] == ["it", "en"]


def test_http_403_is_not_bypassed_by_generic_provider():
    fallback_calls = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        return httpx.Response(403, request=req)

    generic = PublisherSiteProvider(
        site("pendragon_italia"),
        ProviderHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval_seconds=0,
            max_attempts=1,
            browser_fallback_hosts=(),
            browser_fetch=fallback_calls.append,
        ),
    )
    with pytest.raises(Exception, match="HTTP 403"):
        generic.discover(case())
    assert fallback_calls == []


def test_same_host_redirect_to_robots_denied_path_is_refused():
    visited = []

    def handler(req):
        visited.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(
                200, headers={"content-type": "text/plain"},
                content=b"User-agent: *\nDisallow: /private/\n", request=req,
            )
        if req.url.path == "/it/download/":
            return httpx.Response(
                302, headers={"location": "/private/rulebooks"},
                request=req,
            )
        if req.url.path == "/private/rulebooks":
            raise AssertionError("Disallowed redirect destination was fetched")
        return httpx.Response(404, request=req)

    with pytest.raises(Exception, match="disallowed by site policy"):
        provider(site("pendragon_italia"), handler).discover(case())
    assert not any("/private/rulebooks" in path for path in visited)


def test_robots_403_fails_closed_without_browser_fingerprint():
    visited = []

    def handler(req):
        visited.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(403, request=req)
        raise AssertionError("Site page should never be requested")

    assert provider(site("pendragon_italia"), handler).discover(case()) == ()
    assert all(path.endswith("/robots.txt") for path in visited)


def test_generic_provider_identifies_it_language_without_imposing_it_on_en():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"""<h1>Last Aurora: Frozen Steel</h1>
            <a href='/en/last-aurora-rules-en.pdf'>Download English rules</a>""",
            request=req,
        )

    items = provider(site("pendragon_italia"), handler).discover(case())
    assert items and all(item.language == "en" for item in items)


def test_generic_download_button_does_not_promote_promo_or_cover_pdf():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"""<h1>Last Aurora: Frozen Steel</h1>
              <a href='/it/promo-card-it.pdf'>Download</a>
              <a href='/it/box-art-it.pdf'>Scarica</a>
              <a href='/it/rules-it.pdf'>Scarica il regolamento italiano</a>""",
            request=req,
        )
    items = provider(site("pendragon_italia"), handler).discover(case())
    assert len(items) == 1
    assert items[0].url.endswith("/it/rules-it.pdf")


def test_bounded_catalog_scans_past_100_unrelated_items():
    unrelated = "".join(
        f"<h2>Other game {i} regole IT</h2><a href='/it/?ddownload={i}'>Download</a>"
        for i in range(135)
    )
    html = (
        unrelated
        + "<h2>Last Aurora Acciaio Siderale regole IT</h2>"
        + "<a href='/it/?ddownload=last-aurora-frozen'>Download</a>"
    ).encode()

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404, request=req)
        if req.url.path == "/it/download/":
            return httpx.Response(
                200, headers={"content-type": "text/html"},
                content=html, request=req,
            )
        return httpx.Response(404, request=req)

    result = provider(site("pendragon_italia"), handler).discover(case())
    assert len(result) == 1
    assert result[0].url.endswith("ddownload=last-aurora-frozen")
