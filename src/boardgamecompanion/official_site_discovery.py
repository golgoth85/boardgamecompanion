"""Publisher-first rulebook discovery on *verified* official site origins.

The registry contains publisher -> official site assertions, not game-specific
download URLs. Unknown issuers cannot be promoted to official automatically.
All requests are bounded, obey robots directives and remain on a pinned origin.
PDF transfer is deliberately delegated to the existing guarded fetcher.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import quote, urljoin, urlsplit

from boardgamecompanion.rulebooks import (
    RulebookCandidate,
    RulebookProviderError,
    RulebookQuery,
    RulebookSource,
    canonical_http_url,
)
from boardgamecompanion.rulebook_providers import (
    ProviderHttpClient,
    _bgg_id_from_url,
    _dropbox_direct_download,
    _language_from_url,
    _match_text,
    _parse_heading_download_catalog,
    _parse_official_page,
    _slug,
    _strip_italian_rulebook_suffix,
)

MAX_SITE_PAGES = 10
MAX_SITE_SEARCH_TERMS = 3
MAX_SITE_CANDIDATES = 4
USER_AGENT = "BoardGameCompanion/0.2 (official-rulebook-discovery)"


@dataclass(frozen=True, slots=True)
class PublisherSite:
    key: str
    aliases: tuple[str, ...]
    hosts: frozenset[str]
    search_templates: tuple[str, ...] = ()
    entry_urls: tuple[str, ...] = ()
    product_path_parts: tuple[str, ...] = ("/product/", "/prodotto/", "/project/")
    download_hosts: frozenset[str] = frozenset()
    localizer: bool = True
    italian_site: bool = False


# Domain ownership and publisher aliases are curated, never inferred from search
# snippets or from untrusted HTML. Adding a publisher requires data, not an adapter.
VERIFIED_PUBLISHER_SITES: tuple[PublisherSite, ...] = (
    PublisherSite(
        key="repos_production",
        aliases=("Repos Production", "Sombreros Production"),
        hosts=frozenset({"www.rprod.com", "rprod.com"}),
        search_templates=("https://www.rprod.com/en/games/{slug}",),
        product_path_parts=("/en/games/",),
        download_hosts=frozenset({"cdn.svc.asmodee.net"}),
        localizer=False,
    ),
    PublisherSite(
        key="asmodee_italia",
        aliases=("Asmodee Italia", "Asmodee"),
        hosts=frozenset({"www.asmodee.it", "asmodee.it"}),
        search_templates=("https://www.asmodee.it/product/{slug}/",),
        download_hosts=frozenset({"cdn.svc.asmodee.net"}),
        italian_site=True,
    ),
    PublisherSite(
        key="pendragon_italia",
        aliases=("Pendragon Game Studio", "Pendragon Games", "Pendragon"),
        hosts=frozenset({"pendragongamestudio.com", "www.pendragongamestudio.com"}),
        entry_urls=("https://pendragongamestudio.com/it/download/",),
        search_templates=(
            "https://pendragongamestudio.com/it/?s={term}",
            "https://pendragongamestudio.com/it/product/{slug}/",
        ),
        product_path_parts=("/it/product/", "/it/project/"),
        italian_site=True,
    ),
    PublisherSite(
        key="ms_edizioni",
        aliases=("MS Edizioni",),
        hosts=frozenset({"www.msedizioni.it", "msedizioni.it"}),
        search_templates=(
            "https://www.msedizioni.it/?s={term}&post_type=product",
            "https://www.msedizioni.it/prodotto/{slug}/",
        ),
        download_hosts=frozenset({"www.dropbox.com", "dropbox.com"}),
        italian_site=True,
    ),
    PublisherSite(
        key="ghenos_games",
        aliases=("Ghenos Games", "Ghenos"),
        hosts=frozenset({"www.ghenosgames.com", "ghenosgames.com"}),
        search_templates=("https://www.ghenosgames.com/it/?s={term}",),
        italian_site=True,
    ),
)


class PublisherSiteResolver:
    """Only names of known publishers/localizers select a pinned official site."""

    def __init__(self, sites: tuple[PublisherSite, ...] = VERIFIED_PUBLISHER_SITES):
        self.sites = sites

    def resolve(self, query: RulebookQuery) -> tuple[PublisherSite, ...]:
        edition = {_match_text(name) for name in query.edition_publishers}
        verified = {_match_text(name) for name in query.verified_publishers}
        # CSV version publisher is a useful *hint*, not independent proof.
        unverified = {_match_text(name) for name in query.publishers}
        ranked: list[tuple[int, PublisherSite]] = []
        for site in self.sites:
            names = {_match_text(name) for name in site.aliases}
            if names & edition:
                ranked.append((0, site))
            elif names & verified:
                ranked.append((1, site))
            elif names & unverified:
                ranked.append((2, site))
        return tuple(site for _, site in sorted(ranked, key=lambda item: (item[0], item[1].key)))


class PublisherSiteProvider:
    """Shared bounded search algorithm; per-publisher instances isolate failures."""

    def __init__(self, site: PublisherSite, http: ProviderHttpClient | None = None):
        self.site = site
        self.name = f"official_site_{site.key}"
        self.http = http or ProviderHttpClient()
        self._robots: robotparser.RobotFileParser | bool | None = None

    def _allowed_url(self, url: str, *, pdf: bool = False) -> str | None:
        try:
            normalized = canonical_http_url(url)
            parts = urlsplit(normalized)
            hosts = self.site.hosts | (self.site.download_hosts if pdf else frozenset())
            if parts.scheme != "https" or parts.port not in (None, 443):
                return None
            if (parts.hostname or "").lower() not in hosts:
                return None
            return normalized
        except ValueError:
            return None

    def _robots_allows(self, url: str) -> bool:
        if self._robots is None:
            # There is no default allow on an inaccessible robots policy.
            host = (urlsplit(url).hostname or "").lower()
            robots_url = f"https://{host}/robots.txt"
            result = self.http.get(
                robots_url,
                allowed_hosts=self.site.hosts,
                accepted_statuses=frozenset({200, 403, 404}),
            )
            if result.status_code == 403:
                self._robots = False
            elif result.status_code == 404:
                self._robots = True
            else:
                parser = robotparser.RobotFileParser()
                try:
                    parser.parse(result.content.decode("utf-8", "strict").splitlines())
                except (UnicodeError, ValueError, RecursionError) as exc:
                    raise RulebookProviderError("Official robots policy cannot be parsed") from exc
                self._robots = parser
        if isinstance(self._robots, bool):
            return self._robots
        return self._robots.can_fetch(USER_AGENT, url)

    def _get(self, url: str):
        normalized = self._allowed_url(url)
        if normalized is None:
            return None
        if not self._robots_allows(normalized):
            return None
        response = self.http.get(
            normalized,
            allowed_hosts=self.site.hosts,
            accepted_statuses=frozenset({200, 404}),
        )
        if response.status_code == 404:
            return None
        if "application/pdf" in response.content_type.lower():
            return None  # PDF bytes belong to guarded fetch, not discovery.
        if response.content_type and not any(
            content_type in response.content_type.lower()
            for content_type in ("text/html", "application/xhtml", "text/plain")
        ):
            return None
        return response

    @staticmethod
    def _titles(query: RulebookQuery) -> tuple[str, ...]:
        values = (
            *query.verified_titles,
            query.title,
            query.original_title,
        )
        return tuple(dict.fromkeys(
            _match_text(item) for item in values if item and _match_text(item)
        ))

    @staticmethod
    def _search_terms(query: RulebookQuery) -> tuple[str, ...]:
        values = (query.title, query.original_title, *query.verified_titles)
        terms: list[str] = []
        for value in values:
            if not value:
                continue
            clean = " ".join(value.split())
            if clean.casefold() not in {v.casefold() for v in terms}:
                terms.append(clean)
            if len(terms) >= MAX_SITE_SEARCH_TERMS:
                break
        # Full title and a distinctive final token cover localized product slugs.
        for value in values:
            if value:
                words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", value)
                for word in sorted(words, key=lambda w: -len(w)):
                    if len(word) >= 6 and word.casefold() not in {
                        v.casefold() for v in terms
                    }:
                        terms.append(word)
                    if len(terms) >= MAX_SITE_SEARCH_TERMS:
                        break
            if len(terms) >= MAX_SITE_SEARCH_TERMS:
                break
        return tuple(terms[:MAX_SITE_SEARCH_TERMS])

    def _identity(
        self, query: RulebookQuery, title: str, bgg_ids: set[int]
    ) -> tuple[int, int | None, list[str]]:
        expected = set(self._titles(query))
        exact_title = _match_text(title) in expected
        exact_bgg = bgg_ids == {query.bgg_id}
        verified_title = exact_title and _match_text(title) in {
            _match_text(value) for value in query.verified_titles
        }
        publisher_is_bgg_verified = bool(
            {_match_text(name) for name in query.verified_publishers}
            & {_match_text(name) for name in self.site.aliases}
        )
        evidence = ["curated_official_publisher_site"]
        if exact_title:
            evidence.append("page_title_exact")
        if exact_bgg:
            evidence.append("page_bgg_id_exact")
        if publisher_is_bgg_verified:
            evidence.append("bgg_verified_publisher")
        if query.edition_publishers:
            evidence.append("edition_publisher_hint")
        # Link to the exact BGG ID alone is not enough when a product page
        # discusses several different games. Conversely, full title + a
        # BGG-verified publisher is an acceptable cross-check.
        strong = query.bgg_identity_verified and (
            exact_bgg and exact_title
            or verified_title and publisher_is_bgg_verified
        )
        if not (exact_title or exact_bgg):
            return 0, None, evidence
        return (100, query.bgg_id, evidence) if strong else (90, None, evidence)

    def _candidate(
        self,
        query: RulebookQuery,
        *,
        page_url: str,
        title: str,
        pdf_url: str,
        label: str,
        bgg_ids: set[int],
        catalog: bool = False,
    ) -> RulebookCandidate | None:
        normalized = self._allowed_url(pdf_url, pdf=True)
        if normalized is None:
            return None
        parts = urlsplit(normalized)
        allowed_filename = parts.path.lower().endswith(".pdf")
        is_pendragon_download = (
            "ddownload=" in parts.query and
            (parts.hostname or "").lower() in self.site.hosts
        )
        is_dropbox = (parts.hostname or "").lower() in {"www.dropbox.com", "dropbox.com"}
        description = _match_text(label)
        if not (allowed_filename or is_pendragon_download or is_dropbox):
            return None
        if not any(value in description for value in (
            "regolamento", "regole", "rules", "rulebook", "manual", "scarica", "download"
        )) and not re.search(r"(rule|regol|manual)", parts.path, re.I):
            return None

        confidence, bgg_id, evidence = self._identity(query, title, bgg_ids)
        if catalog and _match_text(title) in {
            _match_text(value) for value in query.verified_titles
        }:
            evidence.append("official_download_catalog_title_exact")
        if not confidence:
            return None

        explicit_it = (
            _language_from_url(normalized, label).split("-", 1)[0] == "it"
            or bool(re.search(r"\b(?:italiano|italiana|italian|ita)\b", label, re.I))
            or bool(re.search(r"\b(?:regole|regolamento)\s+it\b", title, re.I))
        )
        if explicit_it:
            language = "it"
            evidence.append("italian_language_explicit")
        elif self.site.italian_site and (
            "regolamento" in description or "regole" in description
        ):
            language = "it"
            evidence.append("italian_page_language_inferred")
            # An Italian storefront can link an English PDF. Require human
            # approval where no explicit IT label/path was observed.
            confidence = min(confidence, 90)
            bgg_id = None
        else:
            language = _language_from_url(normalized, label)
            if language.split("-", 1)[0] not in {"it", "en"}:
                return None

        if is_dropbox:
            normalized = _dropbox_direct_download(normalized)
            evidence.append("publisher_linked_external_download")
        return RulebookCandidate(
            provider=self.name,
            source_kind=(
                RulebookSource.OFFICIAL_LOCALIZER
                if self.site.localizer else RulebookSource.OFFICIAL_PUBLISHER
            ),
            url=normalized,
            language=language,
            document_type="rulebook",
            official=True,
            confidence=confidence,
            bgg_id=bgg_id,
            title=f"{title} — Rules",
            game_title=title,
            publisher=self.site.aliases[0],
            metadata={
                "official_page": page_url,
                "publisher_site": self.site.key,
                "identity_evidence": evidence,
                "catalog_item_type": query.item_type,
            },
        )

    def discover(self, query: RulebookQuery) -> tuple[RulebookCandidate, ...]:
        if self.site not in PublisherSiteResolver().resolve(query):
            return ()
        titles = self._titles(query)
        if not titles:
            return ()

        paths = list(self.site.entry_urls)
        for term in self._search_terms(query):
            for template in self.site.search_templates:
                paths.append(
                    template.format(term=quote(term, safe=""), slug=quote(_slug(term), safe="-"))
                )

        seen_pages: set[str] = set()
        found: list[RulebookCandidate] = []
        seen_pdf: set[str] = set()
        page_count = 0
        while paths and page_count < MAX_SITE_PAGES and len(found) < MAX_SITE_CANDIDATES:
            target = self._allowed_url(paths.pop(0))
            if target is None or target in seen_pages:
                continue
            seen_pages.add(target)
            response = self._get(target)
            page_count += 1
            if response is None:
                continue
            parser = _parse_official_page(response.content)
            heading_parser = _parse_heading_download_catalog(response.content)
            bgg_ids = {
                value for href, _label in parser.links
                for value in (_bgg_id_from_url(urljoin(response.url, href)),)
                if value is not None
            }

            # Index pages may group links by exact heading rather than product URL.
            if target in self.site.entry_urls:
                for heading, href, label in heading_parser.entries:
                    title = _strip_italian_rulebook_suffix(heading)
                    if title not in titles:
                        continue
                    item = self._candidate(
                        query, page_url=response.url, title=title,
                        pdf_url=urljoin(response.url, href), label=label,
                        bgg_ids=set(), catalog=True,
                    )
                    if item and item.url not in seen_pdf:
                        found.append(item)
                        seen_pdf.add(item.url)

            title = parser.title
            if title and (_match_text(title) in titles or bgg_ids == {query.bgg_id}):
                for href, label in parser.links:
                    item = self._candidate(
                        query, page_url=response.url, title=title,
                        pdf_url=urljoin(response.url, href), label=label,
                        bgg_ids=bgg_ids,
                    )
                    if item and item.url not in seen_pdf:
                        found.append(item)
                        seen_pdf.add(item.url)
                        if len(found) >= MAX_SITE_CANDIDATES:
                            break
            # Follow only product-path links on the same pinned origin. Broad
            # link crawling is deliberately forbidden, even inside an issuer site.
            for href, label in parser.links[:100]:
                absolute = self._allowed_url(urljoin(response.url, href))
                if not absolute or absolute in seen_pages:
                    continue
                path = urlsplit(absolute).path.lower()
                if not any(marker in path for marker in self.site.product_path_parts):
                    continue
                if (
                    _match_text(label) in titles
                    or any(_slug(term) in path for term in self._search_terms(query))
                ):
                    paths.append(absolute)
        return tuple(found[:MAX_SITE_CANDIDATES])
