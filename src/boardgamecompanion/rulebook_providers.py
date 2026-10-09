from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from boardgamecompanion.rulebooks import (
    RulebookCandidate,
    RulebookProvider,
    RulebookProviderError,
    RulebookQuery,
    RulebookSource,
    canonical_http_url,
)

MAX_DISCOVERY_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_DISCOVERY_RESULTS = 100
MAX_DISCOVERY_REDIRECTS = 2


class ProviderHttpError(RulebookProviderError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderHttpResponse:
    url: str
    status_code: int
    content_type: str
    content: bytes


class ProviderHttpClient:
    """Bounded HTTP client for fixed provider origins.

    It is intentionally not a rulebook downloader. PDF bytes are still fetched only
    by P5B after P6A approval. This client reads small HTML/JSON indexes, refuses
    cross-origin redirects, applies a per-instance rate gate and bounds retries.
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = MAX_DISCOVERY_RESPONSE_BYTES,
        max_attempts: int = 2,
        min_interval_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        rate_limiter: Callable[[str, float], None] | None = None,
        browser_fallback_hosts: Iterable[str] = (),
        browser_fetch: Callable[[str], httpx.Response] | None = None,
        user_agent: str | None = None,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")
        self.client = client
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)
        self.max_attempts = int(max_attempts)
        self.min_interval_seconds = float(min_interval_seconds)
        self._sleep = sleep
        self._monotonic = monotonic
        self._persistent_rate_limiter = rate_limiter
        self.browser_fallback_hosts = frozenset(
            str(host).strip().lower()
            for host in browser_fallback_hosts
            if str(host).strip()
        )
        self._browser_fetch = browser_fetch
        self.user_agent = user_agent or (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        )
        self._gate_lock = threading.Lock()
        self._last_request_at: float | None = None

    def _rate_gate(self, host: str) -> None:
        if self._persistent_rate_limiter is not None:
            self._persistent_rate_limiter(
                f"rulebook-provider:{host}",
                self.min_interval_seconds,
            )
            return
        with self._gate_lock:
            now = self._monotonic()
            if self._last_request_at is not None:
                remaining = (
                    self.min_interval_seconds - (now - self._last_request_at)
                )
                if remaining > 0:
                    self._sleep(remaining)
            self._last_request_at = self._monotonic()

    @staticmethod
    def _validate_origin(url: str, allowed_hosts: frozenset[str]) -> str:
        canonical = canonical_http_url(url)
        parts = urlsplit(canonical)
        if parts.scheme != "https":
            raise ProviderHttpError("Discovery providers require HTTPS")
        host = (parts.hostname or "").lower()
        if host not in allowed_hosts:
            raise ProviderHttpError(
                f"Discovery redirect escaped the provider origin: {host}"
            )
        return canonical

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            raw = response.headers.get("retry-after", "").strip()
            if raw.isdigit():
                return min(float(raw), 5.0)
        return min(0.25 * (2**attempt), 2.0)

    def _browser_get_once(self, url: str) -> httpx.Response:
        if self._browser_fetch is not None:
            return self._browser_fetch(url)

        try:
            from curl_cffi import requests as curl_requests

            with curl_requests.Session(
                timeout=self.timeout_seconds,
                trust_env=False,
                allow_redirects=False,
                impersonate="chrome",
            ) as session:
                response = session.get(
                    url,
                    headers={
                        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
                        "Cache-Control": "no-cache",
                    },
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                    stream=True,
                )
                try:
                    declared = str(response.headers.get("content-length", "")).strip()
                    if declared.isdigit() and int(declared) > self.max_response_bytes:
                        raise ProviderHttpError("Provider response exceeds the byte limit")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_content():
                        size += len(chunk)
                        if size > self.max_response_bytes:
                            raise ProviderHttpError("Provider response exceeds the byte limit")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    return httpx.Response(
                        int(response.status_code),
                        headers=dict(response.headers),
                        content=content,
                        request=httpx.Request("GET", url),
                    )
                finally:
                    response.close()
        except ProviderHttpError:
            raise
        except Exception as exc:
            raise ProviderHttpError(
                "Provider browser fallback request failed"
            ) from exc

    def get(
        self,
        url: str,
        *,
        allowed_hosts: Iterable[str],
        accepted_statuses: frozenset[int] = frozenset({200}),
        redirect_validator: Callable[[str], bool] | None = None,
    ) -> ProviderHttpResponse:
        hosts = frozenset(str(host).strip().lower() for host in allowed_hosts)
        if not hosts:
            raise ValueError("allowed_hosts must not be empty")
        current = self._validate_origin(url, hosts)
        redirects = 0
        attempt = 0

        while True:
            self._rate_gate((urlsplit(current).hostname or "").lower())
            response: httpx.Response | None = None
            content = b""
            try:
                client_context = (
                    nullcontext(self.client)
                    if self.client is not None
                    else httpx.Client(
                        timeout=self.timeout_seconds,
                        follow_redirects=False,
                        trust_env=False,
                    )
                )
                with client_context as client:
                    assert client is not None
                    with client.stream(
                        "GET",
                        current,
                        headers={
                            "Accept": (
                                "text/html,application/xhtml+xml,"
                                "application/json;q=0.9,*/*;q=0.8"
                            ),
                            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
                            "Accept-Encoding": "identity",
                            "Cache-Control": "no-cache",
                            "User-Agent": self.user_agent,
                        },
                        timeout=self.timeout_seconds,
                        follow_redirects=False,
                    ) as streamed:
                        response = streamed
                        content_encoding = streamed.headers.get(
                            "content-encoding", ""
                        ).strip().casefold()
                        if content_encoding not in {"", "identity"}:
                            raise ProviderHttpError(
                                "Provider response content encoding is not allowed"
                            )
                        declared = streamed.headers.get("content-length", "").strip()
                        if declared.isdigit() and int(declared) > self.max_response_bytes:
                            raise ProviderHttpError("Provider response exceeds the byte limit")
                        if streamed.status_code not in {301, 302, 303, 307, 308}:
                            chunks: list[bytes] = []
                            size = 0
                            for chunk in streamed.iter_bytes():
                                size += len(chunk)
                                if size > self.max_response_bytes:
                                    raise ProviderHttpError("Provider response exceeds the byte limit")
                                chunks.append(chunk)
                            content = b"".join(chunks)
            except httpx.TimeoutException as exc:
                if attempt + 1 < self.max_attempts:
                    self._sleep(self._retry_delay(None, attempt))
                    attempt += 1
                    continue
                raise ProviderHttpError("Provider request timed out") from exc
            except httpx.RequestError as exc:
                if attempt + 1 < self.max_attempts:
                    self._sleep(self._retry_delay(None, attempt))
                    attempt += 1
                    continue
                raise ProviderHttpError("Provider request failed") from exc

            assert response is not None
            current_host = (urlsplit(current).hostname or "").lower()
            if (
                response.status_code == 403
                and current_host in self.browser_fallback_hosts
            ):
                response = self._browser_get_once(current)
                content = response.content

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location or redirects >= MAX_DISCOVERY_REDIRECTS:
                    raise ProviderHttpError("Provider redirect is invalid or excessive")
                next_url = self._validate_origin(urljoin(current, location), hosts)
                if redirect_validator is not None and not redirect_validator(next_url):
                    raise ProviderHttpError("Provider redirect is disallowed by site policy")
                current = next_url
                redirects += 1
                attempt = 0
                continue

            if (
                response.status_code in {408, 429}
                or 500 <= response.status_code <= 599
            ) and attempt + 1 < self.max_attempts:
                self._sleep(self._retry_delay(response, attempt))
                attempt += 1
                continue

            if response.status_code not in accepted_statuses:
                raise ProviderHttpError(
                    f"Provider returned HTTP {response.status_code}"
                )

            return ProviderHttpResponse(
                url=current,
                status_code=response.status_code,
                content_type=response.headers.get("content-type", "")[:200],
                content=content,
            )


def _match_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _slug(value: str) -> str:
    return _match_text(value).replace(" ", "-")


def _publisher_matches(query: RulebookQuery, names: Iterable[str]) -> bool:
    return _publisher_values_match(query.publishers, names)


def _verified_publisher_matches(query: RulebookQuery, names: Iterable[str]) -> bool:
    return query.bgg_identity_verified and _publisher_values_match(
        query.verified_publishers,
        names,
    )


def _publisher_values_match(values: Iterable[str], names: Iterable[str]) -> bool:
    expected = {_match_text(value) for value in names if _match_text(value)}
    return any(
        publisher in expected
        for publisher in (_match_text(value) for value in values)
        if publisher
    )


def _title_matches(query: RulebookQuery, observed: str | None) -> bool:
    value = _match_text(observed)
    return bool(
        value
        and value
        in {
            _match_text(query.title),
            _match_text(query.original_title),
        }
    )


def _verified_title_matches(query: RulebookQuery, observed: str | None) -> bool:
    value = _match_text(observed)
    return bool(
        query.bgg_identity_verified
        and value
        and value in {_match_text(title) for title in query.verified_titles}
    )


class _OfficialPageParser(HTMLParser):
    def __init__(self, *, link_limit: int = MAX_DISCOVERY_RESULTS):
        super().__init__(convert_charrefs=True)
        self._link_limit = link_limit
        self._title_depth = 0
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.title_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "h1":
            self._title_depth += 1
        if tag.lower() == "a" and len(self.links) < self._link_limit:
            href = attributes.get("href")
            if href and len(href) <= 4096:
                self._anchor_href = href
                self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "h1" and self._title_depth:
            self._title_depth -= 1
        if tag.lower() == "a" and self._anchor_href is not None:
            self.links.append(
                (self._anchor_href, " ".join(self._anchor_text).strip())
            )
            self._anchor_href = None
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._title_depth and len(" ".join(self.title_parts)) < 2000:
            self.title_parts.append(data)
        if self._anchor_href is not None and len(" ".join(self._anchor_text)) < 2000:
            self._anchor_text.append(data)

    @property
    def title(self) -> str:
        return " ".join(" ".join(self.title_parts).split())


def _parse_official_page(
    content: bytes, *, link_limit: int = MAX_DISCOVERY_RESULTS
) -> _OfficialPageParser:
    try:
        text = content.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RulebookProviderError("Provider HTML is not valid UTF-8") from exc
    parser = _OfficialPageParser(link_limit=link_limit)
    try:
        parser.feed(text)
        parser.close()
    except (ValueError, RecursionError) as exc:
        raise RulebookProviderError("Provider HTML could not be parsed safely") from exc
    return parser


def _language_from_url(url: str, label: str = "") -> str:
    parts = [part.casefold() for part in urlsplit(url).path.split("/")]
    aliases = {
        "it": "it",
        "en": "en",
        "gb": "en-GB",
        "us": "en-US",
        "fr": "fr",
        "de": "de",
        "es": "es",
        "sp": "es",
        "nl": "nl",
        "pl": "pl",
        "kr": "ko",
    }
    for part in reversed(parts):
        if part in aliases:
            return aliases[part]
    clean_label = _match_text(label)
    return aliases.get(clean_label, "und")


class ReposProductionProvider:
    name = "repos_production"
    _BASE = "https://www.rprod.com/en/games/"
    _HOSTS = frozenset({"www.rprod.com", "rprod.com"})
    _PUBLISHERS = (
        "Repos Production",
        "Sombreros Production",
        "Asmodee",
    )
    _PDF_HOSTS = frozenset({"cdn.svc.asmodee.net", "www.rprod.com", "rprod.com"})

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient()

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        publisher_compatible = _publisher_matches(query, self._PUBLISHERS)
        if not publisher_compatible:
            return ()

        seen_pages: set[str] = set()
        candidates: list[RulebookCandidate] = []
        pages: list[tuple[str, str | None, str]] = []
        for title in (query.title, query.original_title):
            if not title:
                continue
            # Repos hosts expansions below their *parent game's* canonical
            # slug, e.g. /en/games/7-wonders-duel/pantheon. The page H1
            # contains only "Pantheon". Never infer this path for a base game.
            if query.item_type == "boardgameexpansion" and ":" in title:
                parent, suffix = (part.strip() for part in title.rsplit(":", 1))
                if _slug(parent) and _slug(suffix):
                    pages.append(
                        (
                            f"{self._BASE}{quote(_slug(parent), safe='-')}/"
                            f"{quote(_slug(suffix), safe='-')}",
                            suffix,
                            title,
                        )
                    )
            # The legacy flattened slug is only a fallback. Repos may return
            # HTTP 500 (rather than 404) for nonexistent flattened paths, so
            # asking it first can suppress a valid canonical nested page.
            pages.append(
                (f"{self._BASE}{quote(_slug(title), safe='-')}", None, title)
            )

        for page_url, expected_expansion_heading, matched_query_title in pages:
            if page_url in seen_pages:
                continue
            seen_pages.add(page_url)
            response = self.http.get(
                page_url,
                allowed_hosts=self._HOSTS,
                accepted_statuses=frozenset({200, 404}),
            )
            if response.status_code == 404:
                continue
            page = _parse_official_page(response.content)
            nested_expansion_match = (
                expected_expansion_heading is not None
                and _match_text(page.title) == _match_text(expected_expansion_heading)
            )
            if not (_title_matches(query, page.title) or nested_expansion_match):
                continue
            # The observed short expansion heading can be used as part of an
            # exact canonical parent/child path, but it is *not* independent
            # BGG identity evidence. Only an exact, API-verified full title
            # and publisher may carry the canonical BGG ID into P6A.
            identity_verified = _verified_publisher_matches(
                query, self._PUBLISHERS
            ) and _verified_title_matches(
                query,
                matched_query_title if nested_expansion_match else page.title,
            )

            seen_languages: set[str] = set()
            for href, label in page.links:
                absolute = urljoin(response.url, href)
                absolute_parts = urlsplit(absolute)
                if absolute_parts.scheme != "https" or (absolute_parts.hostname or "").lower() not in self._PDF_HOSTS:
                    continue
                path = urlsplit(absolute).path.casefold()
                filename = path.rsplit("/", 1)[-1]
                if not filename.endswith(".pdf"):
                    continue
                if not re.search(r"(?:^|[-_])(rule|rules|regle|regles)(?:[-_.]|$)", filename):
                    continue
                language = _language_from_url(absolute, label)
                if language.split("-", 1)[0] not in {"it", "en"}:
                    continue
                primary_language = language.split("-", 1)[0]
                if primary_language in seen_languages:
                    # Official pages may also list promo/goodie leaflets after the
                    # primary rulebook. Preserve one authoritative manual per
                    # requested language instead of misclassifying those add-ons.
                    continue
                seen_languages.add(primary_language)
                candidates.append(
                    RulebookCandidate(
                        provider=self.name,
                        source_kind=RulebookSource.OFFICIAL_PUBLISHER,
                        url=absolute,
                        language=language,
                        document_type="rulebook",
                        official=True,
                        confidence=100,
                        title=(
                            f"{matched_query_title} — Rules"
                            if nested_expansion_match
                            else f"{page.title} — Rules"
                        ),
                        bgg_id=query.bgg_id if identity_verified else None,
                        game_title=(
                            matched_query_title if nested_expansion_match else page.title
                        ),
                        year=None,
                        publisher="Repos Production",
                        metadata={
                            "official_page": response.url,
                            "identity_evidence": (
                                (
                                    [
                                        "official_nested_expansion_path_and_heading",
                                        "bgg_api_exact_id_title_publisher_crosscheck",
                                    ]
                                    if nested_expansion_match
                                    else [
                                        "official_page_title_exact",
                                        "bgg_api_exact_id_title_publisher_crosscheck",
                                    ]
                                )
                                if identity_verified
                                else (
                                    ["official_nested_expansion_path_and_heading", "catalog_publisher_compatible"]
                                    if nested_expansion_match
                                    else ["official_page_title_exact", "catalog_publisher_compatible"]
                                )
                            ),
                            "catalog_item_type": query.item_type,
                        },
                    )
                )
            if candidates:
                break
        return tuple(candidates[:MAX_DISCOVERY_RESULTS])


class AsmodeeItaliaProvider:
    name = "asmodee_italia"
    _BASE = "https://www.asmodee.it/product/"
    _HOSTS = frozenset({"www.asmodee.it", "asmodee.it"})
    _PUBLISHERS = ("Asmodee", "Asmodee Italia")
    _PDF_HOSTS = frozenset(
        {"cdn.svc.asmodee.net", "www.asmodee.it", "asmodee.it", "www.rprod.com", "rprod.com"}
    )
    _RULEBOOK_PAGE_HOSTS = frozenset({"www.rprod.com", "rprod.com"})

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient()

    def _candidate(
        self,
        *,
        query: RulebookQuery,
        page: _OfficialPageParser,
        official_page_url: str,
        pdf_url: str,
        identity_verified: bool,
        rulebook_page_url: str | None = None,
    ) -> RulebookCandidate:
        evidence = ["official_page_title_exact"]
        if identity_verified:
            evidence.append("bgg_api_exact_id_title_crosscheck")
        metadata: dict[str, object] = {
            "official_page": official_page_url,
            "identity_evidence": evidence,
            "catalog_item_type": query.item_type,
        }
        if rulebook_page_url is not None:
            metadata["rulebook_page"] = rulebook_page_url
        return RulebookCandidate(
            provider=self.name,
            source_kind=RulebookSource.OFFICIAL_LOCALIZER,
            url=pdf_url,
            language="it",
            document_type="rulebook",
            official=True,
            confidence=100 if identity_verified else 94,
            title=f"{page.title} — Regolamento italiano",
            bgg_id=query.bgg_id if identity_verified else None,
            game_title=page.title,
            year=None,
            publisher="Asmodee Italia",
            metadata=metadata,
        )

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        seen_pages: set[str] = set()
        for title in (query.title, query.original_title):
            if not title:
                continue
            page_url = f"{self._BASE}{quote(_slug(title), safe='-')}/"
            if page_url in seen_pages:
                continue
            seen_pages.add(page_url)
            response = self.http.get(
                page_url,
                allowed_hosts=self._HOSTS,
                accepted_statuses=frozenset({200, 404}),
            )
            if response.status_code == 404:
                continue
            page = _parse_official_page(response.content)
            if not _title_matches(query, page.title):
                continue

            # BGG has already bound query.bgg_id to an exact verified title. For an
            # official localizer page, an exact title match is sufficient identity
            # evidence even when the localizer is not listed as the BGG publisher.
            identity_verified = query.bgg_identity_verified and _verified_title_matches(
                query, page.title
            )

            candidates: list[RulebookCandidate] = []
            for href, label in page.links:
                if "regolamento" not in _match_text(label):
                    continue
                absolute = urljoin(response.url, href)
                parts = urlsplit(absolute)
                host = (parts.hostname or "").lower()
                if parts.scheme != "https":
                    continue

                if host in self._PDF_HOSTS and parts.path.casefold().endswith(".pdf"):
                    candidates.append(
                        self._candidate(
                            query=query,
                            page=page,
                            official_page_url=response.url,
                            pdf_url=absolute,
                            identity_verified=identity_verified,
                        )
                    )
                    continue

                # Asmodee Italia currently links some "Scarica il regolamento"
                # actions to the official Repos product page rather than directly
                # to the PDF. Follow only that fixed trusted origin and then select
                # the Italian rules PDF from its bounded link list.
                if host not in self._RULEBOOK_PAGE_HOSTS:
                    continue
                linked = self.http.get(
                    absolute,
                    allowed_hosts=self._RULEBOOK_PAGE_HOSTS,
                    accepted_statuses=frozenset({200, 404}),
                )
                if linked.status_code == 404:
                    continue
                rulebook_page = _parse_official_page(linked.content)
                if not _title_matches(query, rulebook_page.title):
                    continue
                for pdf_href, pdf_label in rulebook_page.links:
                    pdf_url = urljoin(linked.url, pdf_href)
                    pdf_parts = urlsplit(pdf_url)
                    if (
                        pdf_parts.scheme != "https"
                        or (pdf_parts.hostname or "").lower() not in self._PDF_HOSTS
                        or not pdf_parts.path.casefold().endswith(".pdf")
                    ):
                        continue
                    filename = pdf_parts.path.casefold().rsplit("/", 1)[-1]
                    if not re.search(
                        r"(?:^|[-_])(rule|rules|regle|regles)(?:[-_.]|$)",
                        filename,
                    ):
                        continue
                    if _language_from_url(pdf_url, pdf_label).split("-", 1)[0] != "it":
                        continue
                    candidates.append(
                        self._candidate(
                            query=query,
                            page=page,
                            official_page_url=response.url,
                            pdf_url=pdf_url,
                            identity_verified=identity_verified,
                            rulebook_page_url=linked.url,
                        )
                    )
                    break
            if candidates:
                return tuple(candidates[:MAX_DISCOVERY_RESULTS])
        return ()



class _HeadingDownloadParser(HTMLParser):
    def __init__(self, *, link_limit: int = MAX_DISCOVERY_RESULTS) -> None:
        super().__init__(convert_charrefs=True)
        self._link_limit = link_limit
        self._heading_depth = 0
        self._heading_parts: list[str] = []
        self._current_heading = ""
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.entries: list[tuple[str, str, str]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        name = tag.lower()
        attributes = dict(attrs)
        if name in {"h2", "h3"}:
            self._heading_depth += 1
            self._heading_parts = []
        if name == "a" and len(self.entries) < self._link_limit:
            href = attributes.get("href")
            if href and len(href) <= 4096:
                self._anchor_href = href
                self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in {"h2", "h3"} and self._heading_depth:
            self._heading_depth -= 1
            if not self._heading_depth:
                self._current_heading = " ".join(
                    " ".join(self._heading_parts).split()
                )[:500]
        if name == "a" and self._anchor_href is not None:
            self.entries.append(
                (
                    self._current_heading,
                    self._anchor_href,
                    " ".join(" ".join(self._anchor_text).split())[:500],
                )
            )
            self._anchor_href = None
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._heading_depth and len(" ".join(self._heading_parts)) < 2000:
            self._heading_parts.append(data)
        if self._anchor_href is not None and len(" ".join(self._anchor_text)) < 2000:
            self._anchor_text.append(data)


def _parse_heading_download_catalog(
    content: bytes, *, link_limit: int = MAX_DISCOVERY_RESULTS
) -> _HeadingDownloadParser:
    try:
        text = content.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RulebookProviderError("Provider HTML is not valid UTF-8") from exc
    parser = _HeadingDownloadParser(link_limit=link_limit)
    try:
        parser.feed(text)
        parser.close()
    except (ValueError, RecursionError) as exc:
        raise RulebookProviderError("Provider HTML could not be parsed safely") from exc
    return parser


def _strip_italian_rulebook_suffix(value: str) -> str:
    clean = _match_text(value)
    clean = re.sub(
        r"\s+(?:regole|rules|regolamento|regolamenti)"
        r"(?:\s+(?:in\s+italiano|italiano|italiana|it|ita))?$",
        "",
        clean,
    )
    clean = re.sub(r"\s+(?:it|ita)$", "", clean)
    return " ".join(clean.split())


def _bgg_id_from_url(value: str) -> int | None:
    try:
        parts = urlsplit(canonical_http_url(value))
    except ValueError:
        return None
    if (parts.hostname or "").lower() not in {
        "boardgamegeek.com",
        "www.boardgamegeek.com",
    }:
        return None
    match = re.search(r"/(?:boardgame|boardgameexpansion)/(\d+)(?:/|$)", parts.path)
    if not match:
        return None
    identifier = int(match.group(1))
    return identifier if identifier > 0 else None


def _dropbox_direct_download(value: str) -> str:
    parts = urlsplit(canonical_http_url(value))
    host = (parts.hostname or "").lower()
    if host not in {"dropbox.com", "www.dropbox.com"}:
        return canonical_http_url(value)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["dl"] = "1"
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), "")
    )


class PendragonItaliaProvider:
    name = "pendragon_italia"
    _INDEX = "https://pendragongamestudio.com/it/download/"
    _HOSTS = frozenset(
        {"pendragongamestudio.com", "www.pendragongamestudio.com"}
    )
    _PUBLISHERS = (
        "Pendragon Game Studio",
        "Pendragon Games",
        "Pendragon",
    )

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient()

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        if not _verified_publisher_matches(query, self._PUBLISHERS):
            return ()

        verified_titles = {
            _match_text(value)
            for value in query.verified_titles
            if _match_text(value)
        }
        if not query.bgg_identity_verified or not verified_titles:
            return ()

        response = self.http.get(
            self._INDEX,
            allowed_hosts=self._HOSTS,
            accepted_statuses=frozenset({200}),
        )
        catalog = _parse_heading_download_catalog(response.content)
        candidates: list[RulebookCandidate] = []
        seen: set[str] = set()

        for heading, href, label in catalog.entries:
            observed_title = _strip_italian_rulebook_suffix(heading)
            if not observed_title or observed_title not in verified_titles:
                continue
            absolute = canonical_http_url(urljoin(response.url, href))
            parts = urlsplit(absolute)
            if (
                parts.scheme != "https"
                or (parts.hostname or "").lower() not in self._HOSTS
            ):
                continue
            label_text = _match_text(label)
            if (
                "download" not in label_text
                and "scarica" not in label_text
                and "ddownload=" not in absolute
            ):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            candidates.append(
                RulebookCandidate(
                    provider=self.name,
                    source_kind=RulebookSource.OFFICIAL_LOCALIZER,
                    url=absolute,
                    language="it",
                    document_type="rulebook",
                    official=True,
                    confidence=100,
                    bgg_id=query.bgg_id,
                    game_title=heading,
                    publisher="Pendragon Game Studio",
                    metadata={
                        "official_page": response.url,
                        "identity_evidence": [
                            "bgg_api_exact_id_publisher_crosscheck",
                            "bgg_verified_title_alias_exact",
                            "official_download_catalog",
                        ],
                        "catalog_item_type": query.item_type,
                    },
                )
            )
            if len(candidates) >= MAX_DISCOVERY_RESULTS:
                break
        return tuple(candidates)


class MsEdizioniProvider:
    name = "ms_edizioni"
    _BASE = "https://www.msedizioni.it/"
    _HOSTS = frozenset({"www.msedizioni.it", "msedizioni.it"})
    _PUBLISHERS = ("MS Edizioni",)
    _DOWNLOAD_HOSTS = frozenset(
        {
            "www.msedizioni.it",
            "msedizioni.it",
            "www.dropbox.com",
            "dropbox.com",
        }
    )

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient()

    @staticmethod
    def _search_terms(query: RulebookQuery) -> tuple[str, ...]:
        values = [
            query.title,
            query.original_title,
            *query.verified_titles,
        ]
        terms: list[str] = []
        for value in values:
            clean = " ".join(str(value or "").split())
            if clean and clean.casefold() not in {item.casefold() for item in terms}:
                terms.append(clean)
        # WordPress search is token based, so a distinctive long token is a
        # useful fallback for localized titles (e.g. "Explorers of Navoria").
        for value in tuple(terms):
            tokens = [
                token
                for token in re.findall(r"[A-Za-zÀ-ÿ0-9]+", value)
                if len(token) >= 6
            ]
            for token in sorted(tokens, key=lambda item: (-len(item), item.casefold())):
                if token.casefold() not in {item.casefold() for item in terms}:
                    terms.append(token)
                if len(terms) >= 8:
                    break
            if len(terms) >= 8:
                break
        return tuple(terms[:8])

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        if not _verified_publisher_matches(query, self._PUBLISHERS):
            return ()
        if not query.bgg_identity_verified:
            return ()

        seen_products: set[str] = set()
        for term in self._search_terms(query):
            search_url = (
                f"{self._BASE}?s={quote(term)}&post_type=product"
            )
            response = self.http.get(
                search_url,
                allowed_hosts=self._HOSTS,
                accepted_statuses=frozenset({200, 404}),
            )
            if response.status_code == 404:
                continue
            search_page = _parse_official_page(response.content)
            product_urls: list[str] = []
            for href, _label in search_page.links:
                absolute = canonical_http_url(urljoin(response.url, href))
                parts = urlsplit(absolute)
                if (
                    parts.scheme == "https"
                    and (parts.hostname or "").lower() in self._HOSTS
                    and parts.path.startswith("/prodotto/")
                    and absolute not in seen_products
                ):
                    seen_products.add(absolute)
                    product_urls.append(absolute)
                if len(product_urls) >= 12:
                    break

            for product_url in product_urls:
                product_response = self.http.get(
                    product_url,
                    allowed_hosts=self._HOSTS,
                    accepted_statuses=frozenset({200, 404}),
                )
                if product_response.status_code == 404:
                    continue
                page = _parse_official_page(product_response.content)
                linked_bgg_ids = {
                    identifier
                    for href, _label in page.links
                    for identifier in (_bgg_id_from_url(urljoin(product_response.url, href)),)
                    if identifier is not None
                }
                if query.bgg_id not in linked_bgg_ids:
                    continue

                for href, label in page.links:
                    if "regolamento" not in _match_text(label):
                        continue
                    absolute = canonical_http_url(
                        urljoin(product_response.url, href)
                    )
                    parts = urlsplit(absolute)
                    if (
                        parts.scheme != "https"
                        or (parts.hostname or "").lower() not in self._DOWNLOAD_HOSTS
                    ):
                        continue
                    absolute = _dropbox_direct_download(absolute)
                    return (
                        RulebookCandidate(
                            provider=self.name,
                            source_kind=RulebookSource.OFFICIAL_LOCALIZER,
                            url=absolute,
                            language="it",
                            document_type="rulebook",
                            official=True,
                            confidence=100,
                            bgg_id=query.bgg_id,
                            game_title=page.title or query.title,
                            publisher="MS Edizioni",
                            metadata={
                                "official_page": product_response.url,
                                "identity_evidence": [
                                    "official_page_exact_bgg_link",
                                    "bgg_api_exact_id_publisher_crosscheck",
                                ],
                                "catalog_item_type": query.item_type,
                            },
                        ),
                    )
        return ()



class AwakenRealmsProvider:
    """Official Awaken Realms rulebook discovery via the publisher JSON catalog."""

    name = "awaken_realms"
    _INDEX = "https://awakenrealms.com/data/files.json"
    _HOSTS = frozenset({"awakenrealms.com", "www.awakenrealms.com"})
    _PUBLISHERS = ("Awaken Realms",)
    _MAX_CATALOG_ITEMS = 3000
    _GENERIC_EXPANSION_WORDS = frozenset(
        {
            "expansion",
            "expansions",
            "edition",
            "pack",
            "promo",
            "box",
            "campaign",
        }
    )
    _LANGUAGE_CODES = {
        "it": "it",
        "ita": "it",
        "en": "en",
        "eng": "en",
        "uk": "en",
        "gb": "en",
        "us": "en",
    }

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient()

    @classmethod
    def _language(cls, *, download_url: str, flag_url: object) -> str:
        values: list[str] = []
        if isinstance(flag_url, str):
            values.extend(urlsplit(flag_url).path.split("/"))
        values.extend(urlsplit(download_url).path.split("/"))
        for value in reversed(values):
            token = value.rsplit(".", 1)[0].strip().casefold()
            language = cls._LANGUAGE_CODES.get(token)
            if language:
                return language
        return "und"

    @classmethod
    def _query_match(
        cls,
        query: RulebookQuery,
        catalog_game: str,
    ) -> tuple[str, tuple[str, ...]] | None:
        game = _match_text(catalog_game)
        if not game:
            return None
        titles = tuple(
            dict.fromkeys(
                value
                for raw in (
                    *query.verified_titles,
                    query.title,
                    query.original_title,
                )
                if raw and (value := _match_text(raw))
            )
        )
        for title in titles:
            if title == game:
                return ("base", ())
        if "expansion" not in _match_text(query.item_type):
            return None
        for title in titles:
            prefix = f"{game} "
            if not title.startswith(prefix):
                continue
            suffix = title[len(prefix):].strip()
            tokens = tuple(
                token
                for token in suffix.split()
                if token not in cls._GENERIC_EXPANSION_WORDS
            )
            if tokens:
                return ("expansion", tokens)
        return None

    @classmethod
    def _expansion_match_strength(
        cls,
        suffix_tokens: tuple[str, ...],
        candidate_title: str,
    ) -> str | None:
        observed = tuple(_match_text(candidate_title).split())
        if not observed:
            return None

        def variants(token: str) -> set[str]:
            values = {token}
            if len(token) > 4 and token.endswith("s"):
                values.add(token[:-1])
            return values

        if all(any(value in observed for value in variants(token)) for token in suffix_tokens):
            return "exact_suffix"

        if len(suffix_tokens) >= 2:
            initialism = "".join(token[0] for token in suffix_tokens if token)
            if len(initialism) >= 2 and initialism in observed:
                return "initialism"
        return None

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        if not _verified_publisher_matches(query, self._PUBLISHERS):
            return ()

        response = self.http.get(
            self._INDEX,
            allowed_hosts=self._HOSTS,
            accepted_statuses=frozenset({200}),
        )
        try:
            payload = json.loads(response.content.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise RulebookProviderError(
                "Awaken Realms catalog returned invalid JSON"
            ) from exc
        if not isinstance(payload, list):
            raise RulebookProviderError("Awaken Realms catalog must be a list")
        if len(payload) > self._MAX_CATALOG_ITEMS:
            raise RulebookProviderError("Awaken Realms catalog is unexpectedly large")

        matched: list[
            tuple[
                Mapping[str, Any],
                str,
                str,
                tuple[str, ...],
            ]
        ] = []
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            catalog_game = item.get("game")
            category = item.get("category")
            title = item.get("title")
            raw_url = item.get("downloadUrl")
            if not all(isinstance(value, str) for value in (catalog_game, category, title, raw_url)):
                continue
            if _match_text(category) not in {"rulebook", "rulebooks"}:
                continue
            query_match = self._query_match(query, catalog_game)
            if query_match is None:
                continue
            mode, suffix_tokens = query_match
            try:
                download_url = canonical_http_url(urljoin(response.url, raw_url))
            except ValueError:
                continue
            parts = urlsplit(download_url)
            if (
                parts.scheme != "https"
                or (parts.hostname or "").lower() not in self._HOSTS
                or not parts.path.casefold().endswith(".pdf")
            ):
                continue
            language = self._language(
                download_url=download_url,
                flag_url=item.get("flagUrl"),
            )
            if language not in {"it", "en"}:
                continue
            matched.append((item, download_url, mode, suffix_tokens))

        if not matched:
            return ()

        base_title: str | None = None
        if any(mode == "base" for _, _, mode, _ in matched):
            title_keys = {
                _match_text(str(item["title"]))
                for item, _, mode, _ in matched
                if mode == "base"
            }
            if title_keys:
                by_size = sorted(
                    title_keys,
                    key=lambda value: (len(value.split()), len(value), value),
                )
                minimum_size = len(by_size[0].split())
                minimum = [
                    value for value in by_size
                    if len(value.split()) == minimum_size
                ]
                if len(minimum) == 1:
                    base_title = minimum[0]

        candidates: list[RulebookCandidate] = []
        seen: set[tuple[str, str]] = set()
        for item, download_url, mode, suffix_tokens in matched:
            title = str(item["title"])
            identity_evidence = [
                "curated_official_publisher_catalog",
                "bgg_verified_publisher",
            ]
            confidence = 90
            bgg_id: int | None = None

            if mode == "base":
                if base_title is None or _match_text(title) != base_title:
                    continue
                confidence = 100
                bgg_id = query.bgg_id
                identity_evidence.extend(
                    (
                        "official_catalog_game_title_exact",
                        "official_catalog_unique_base_rulebook",
                    )
                )
            else:
                strength = self._expansion_match_strength(suffix_tokens, title)
                if strength is None:
                    continue
                identity_evidence.append(f"official_catalog_{strength}")
                if strength == "exact_suffix":
                    confidence = 100
                    bgg_id = query.bgg_id
                else:
                    identity_evidence.append("abbreviation_requires_review")

            language = self._language(
                download_url=download_url,
                flag_url=item.get("flagUrl"),
            )
            key = (download_url, language)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                RulebookCandidate(
                    provider=self.name,
                    source_kind=RulebookSource.OFFICIAL_PUBLISHER,
                    url=download_url,
                    language=language,
                    document_type="rulebook",
                    official=True,
                    confidence=confidence,
                    title=title,
                    bgg_id=bgg_id,
                    game_title=query.title,
                    year=query.year,
                    publisher="Awaken Realms",
                    metadata={
                        "official_catalog": response.url,
                        "catalog_game": str(item["game"]),
                        "identity_evidence": identity_evidence,
                        "catalog_item_type": query.item_type,
                    },
                )
            )

        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    0 if candidate.language == "it" else 1,
                    candidate.title or "",
                    candidate.url,
                ),
            )
        )


class FantasyFlightAgotExpansionRulesProvider:
    """Shared official expansion-rules document for AGOT LCG second edition."""

    name = "fantasy_flight_agot_expansion_rules"
    _PUBLISHERS = ("Fantasy Flight Games",)
    _URL = (
        "https://images-cdn.fantasyflightgames.com/filer_public/06/c4/"
        "06c495e8-1769-4d93-b5a9-7c2bdcbcc765/gt_expansion_rules.pdf"
    )
    _SUPPORTED_BGG_IDS = frozenset({
        236435,  # House of Thorns
        262638,  # Kings of the Isles
        201277,  # Lions of Casterly Rock
        245349,  # Sands of Dorne
        217960,  # Watchers on the Wall
        189169,  # Wolves of the North
    })
    @classmethod
    def _identity_matches(cls, query: RulebookQuery) -> bool:
        if query.bgg_id not in cls._SUPPORTED_BGG_IDS:
            return False
        if "expansion" not in _match_text(query.item_type):
            return False
        titles = (
            *query.verified_titles,
            query.title,
            query.original_title,
        )
        return any(
            {
                "game", "thrones", "card"
            }.issubset(set(_match_text(value).split()))
            for value in titles
            if value
        )

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        if (
            not _verified_publisher_matches(query, self._PUBLISHERS)
            or not self._identity_matches(query)
        ):
            return ()

        return (
            RulebookCandidate(
                provider=self.name,
                source_kind=RulebookSource.OFFICIAL_PUBLISHER,
                url=self._URL,
                language="en",
                document_type="rulebook",
                official=True,
                confidence=100,
                title=(
                    "A Game of Thrones: The Card Game — "
                    "Expansion Rules (shared)"
                ),
                bgg_id=query.bgg_id,
                game_title=query.title,
                year=query.year,
                publisher="Fantasy Flight Games",
                metadata={
                    "official_page": (
                        "https://www.fantasyflightgames.com/en/products/"
                        "a-game-of-thrones-the-card-game-second-edition/"
                    ),
                    "identity_evidence": (
                        "curated_official_family_support_page",
                        "bgg_verified_publisher",
                        "curated_supported_expansion_bgg_id",
                    ),
                    "shared_rulebook": True,
                    "shared_scope": "agot_lcg_second_edition_expansions",
                    "catalog_item_type": query.item_type,
                },
            ),
        )



class MonolithBatmanProvider:
    """Official Batman GCC booklets embedded in Monolith's DFlip catalogue."""

    name = "monolith_batman"
    _PAGE = "https://monolithedition.com/en/portfolio/batman-gotham-city-chronicles/"
    _HOSTS = frozenset({"monolithedition.com", "www.monolithedition.com"})
    _PUBLISHERS = ("Monolith Board Games",)
    _DFLIP_RE = re.compile(
        r"window\.df_option_[0-9]+\s*=\s*(\{.*?\})\s*;",
        re.DOTALL,
    )
    _EXPANSION_MATCHES = {
        "arkham asylum": ("arkham", "asylum"),
        "wayne manor": ("wayne", "manor"),
        "versus": ("versus",),
    }

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient(
            browser_fallback_hosts=self._HOSTS,
        )

    @classmethod
    def _wanted_key(cls, query: RulebookQuery) -> str | None:
        if "expansion" not in _match_text(query.item_type):
            return None
        titles = (
            *query.verified_titles,
            query.title,
            query.original_title,
        )
        for raw in titles:
            title = _match_text(raw)
            if not title:
                continue
            for key, tokens in cls._EXPANSION_MATCHES.items():
                if all(token in title.split() for token in tokens):
                    return key
        return None

    @staticmethod
    def _language(source: str) -> str:
        filename = urlsplit(source).path.rsplit("/", 1)[-1]
        if re.search(r"(?:_|-)(?:EN|ENF)(?:[._-]|$)", filename, re.I):
            return "en"
        if re.search(r"(?:_|-)(?:IT|ITA)(?:[._-]|$)", filename, re.I):
            return "it"
        return "und"

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        if not _verified_publisher_matches(query, self._PUBLISHERS):
            return ()
        wanted = self._wanted_key(query)
        if wanted is None:
            return ()

        response = self.http.get(
            self._PAGE,
            allowed_hosts=self._HOSTS,
            accepted_statuses=frozenset({200}),
        )
        try:
            text = response.content.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise RulebookProviderError("Monolith catalogue is not valid UTF-8") from exc

        expected_tokens = self._EXPANSION_MATCHES[wanted]
        candidates: list[RulebookCandidate] = []
        seen: set[str] = set()
        for raw in self._DFLIP_RE.findall(text):
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, RecursionError):
                continue
            if not isinstance(payload, Mapping):
                continue
            source = payload.get("source")
            slug = payload.get("slug")
            if not isinstance(source, str) or not isinstance(slug, str):
                continue
            label = _match_text(f"{slug} {urlsplit(source).path.rsplit('/', 1)[-1]}")
            if not all(token in label.split() for token in expected_tokens):
                continue
            try:
                url = canonical_http_url(source)
            except ValueError:
                continue
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or (parts.hostname or "").lower() not in self._HOSTS
                or not parts.path.casefold().endswith(".pdf")
                or url in seen
            ):
                continue
            language = self._language(url)
            if language not in {"it", "en"}:
                continue
            seen.add(url)
            candidates.append(
                RulebookCandidate(
                    provider=self.name,
                    source_kind=RulebookSource.OFFICIAL_PUBLISHER,
                    url=url,
                    language=language,
                    document_type="rulebook",
                    official=True,
                    confidence=100,
                    title=f"{query.title} — Official booklet",
                    bgg_id=query.bgg_id,
                    game_title=query.title,
                    year=query.year,
                    publisher="Monolith Board Games",
                    metadata={
                        "official_page": response.url,
                        "identity_evidence": (
                            "curated_official_publisher_page",
                            "bgg_verified_publisher",
                            "expansion_booklet_label_exact",
                        ),
                        "catalog_item_type": query.item_type,
                    },
                )
            )
        return tuple(candidates)


class SeriousPoulpProvider:
    """Official 7th Continent download catalogue for expansion rulebooks."""

    name = "serious_poulp"
    _PAGE = "https://the7thcontinent.seriouspoulp.com/en/resources/downloads"
    _HOSTS = frozenset({"the7thcontinent.seriouspoulp.com"})
    _PUBLISHERS = ("Serious Poulp",)

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient()

    @staticmethod
    def _is_wgumcd(query: RulebookQuery) -> bool:
        if "expansion" not in _match_text(query.item_type):
            return False
        values = (
            *query.verified_titles,
            query.title,
            query.original_title,
        )
        return any(
            all(token in _match_text(value).split() for token in ("what", "goes", "up", "must", "come", "down"))
            for value in values
            if value
        )

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        if (
            not _verified_publisher_matches(query, self._PUBLISHERS)
            or not self._is_wgumcd(query)
        ):
            return ()

        response = self.http.get(
            self._PAGE,
            allowed_hosts=self._HOSTS,
            accepted_statuses=frozenset({200}),
        )
        page = _parse_official_page(response.content, link_limit=400)
        candidates: list[RulebookCandidate] = []
        for href, label in page.links:
            observed = _match_text(f"{label} {href}")
            if "wgumcd" not in observed.split():
                continue
            try:
                url = canonical_http_url(urljoin(response.url, href))
            except ValueError:
                continue
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or (parts.hostname or "").lower() not in self._HOSTS
                or not parts.path.casefold().endswith(".pdf")
            ):
                continue
            candidates.append(
                RulebookCandidate(
                    provider=self.name,
                    source_kind=RulebookSource.OFFICIAL_PUBLISHER,
                    url=url,
                    language="en",
                    document_type="rulebook",
                    official=True,
                    confidence=100,
                    title=f"{query.title} — Official rulebook",
                    bgg_id=query.bgg_id,
                    game_title=query.title,
                    year=query.year,
                    publisher="Serious Poulp",
                    metadata={
                        "official_page": response.url,
                        "identity_evidence": (
                            "curated_official_publisher_download_catalog",
                            "bgg_verified_publisher",
                            "wgumcd_expansion_label_exact",
                        ),
                        "catalog_item_type": query.item_type,
                    },
                )
            )
        return tuple(candidates)



class RuleBookOrgProvider:
    name = "rulebook_org"
    _ENDPOINT = "https://api.rule-book.org/games"
    _HOSTS = frozenset({"api.rule-book.org"})

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient()

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        url = f"{self._ENDPOINT}?search={quote(query.title)}&language=en"
        response = self.http.get(url, allowed_hosts=self._HOSTS)
        try:
            payload = json.loads(response.content.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise RulebookProviderError("Community provider returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise RulebookProviderError("Community provider response must be an object")
        results = payload.get("results")
        if not isinstance(results, list):
            raise RulebookProviderError("Community provider results must be a list")
        if len(results) > MAX_DISCOVERY_RESULTS:
            raise RulebookProviderError("Community provider returned too many results")

        expected_titles = {
            value
            for value in (
                _match_text(query.title),
                _match_text(query.original_title),
            )
            if value
        }
        candidates: list[RulebookCandidate] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            raw_name = item.get("name")
            raw_url = item.get("link")
            if not isinstance(raw_name, str) or not isinstance(raw_url, str):
                continue
            normalized_name = _match_text(raw_name)
            for suffix in (" rulebook", " rules", " regle", " regles"):
                if normalized_name.endswith(suffix):
                    normalized_name = normalized_name[: -len(suffix)].strip()
                    break
            if normalized_name not in expected_titles:
                continue
            language = item.get("language", "en")
            candidates.append(
                RulebookCandidate(
                    provider=self.name,
                    source_kind=RulebookSource.COMMUNITY,
                    url=raw_url,
                    language=str(language),
                    document_type="rulebook",
                    official=False,
                    confidence=70,
                    title=raw_name,
                    bgg_id=None,
                    game_title=query.title,
                    year=query.year,
                    metadata={
                        "community_game_id": str(item.get("id") or "")[:500],
                        "identity_evidence": ["exact_title_only"],
                        "catalog_item_type": query.item_type,
                    },
                )
            )
        return tuple(candidates)


def _production_client_factory(
    *,
    timeout_seconds: float,
    max_response_bytes: int,
    max_attempts: int,
    min_interval_seconds: float,
    rate_limiter: Callable[[str, float], None] | None,
):
    def client(*, browser_fallback_hosts: Iterable[str] = ()) -> ProviderHttpClient:
        return ProviderHttpClient(
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_attempts=max_attempts,
            min_interval_seconds=min_interval_seconds,
            rate_limiter=rate_limiter,
            browser_fallback_hosts=browser_fallback_hosts,
        )
    return client


def production_official_rulebook_providers(
    *,
    timeout_seconds: float = 10.0,
    max_response_bytes: int = MAX_DISCOVERY_RESPONSE_BYTES,
    max_attempts: int = 2,
    min_interval_seconds: float = 1.0,
    rate_limiter: Callable[[str, float], None] | None = None,
) -> tuple[RulebookProvider, ...]:
    client = _production_client_factory(
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        max_attempts=max_attempts,
        min_interval_seconds=min_interval_seconds,
        rate_limiter=rate_limiter,
    )

    from boardgamecompanion.official_site_discovery import (
        PublisherSiteProvider,
        VERIFIED_PUBLISHER_SITES,
        USER_AGENT as SITE_USER_AGENT,
    )

    generic_providers = tuple(
        PublisherSiteProvider(
            site,
            ProviderHttpClient(
                timeout_seconds=timeout_seconds,
                max_response_bytes=max_response_bytes,
                max_attempts=max_attempts,
                min_interval_seconds=min_interval_seconds,
                rate_limiter=rate_limiter,
                user_agent=SITE_USER_AGENT,
            ),
        )
        for site in VERIFIED_PUBLISHER_SITES
    )

    return (
        *generic_providers,
        FantasyFlightAgotExpansionRulesProvider(),
        MonolithBatmanProvider(
            client(browser_fallback_hosts=MonolithBatmanProvider._HOSTS)
        ),
        SeriousPoulpProvider(client()),
        AwakenRealmsProvider(client()),
        ReposProductionProvider(
            client(browser_fallback_hosts=ReposProductionProvider._HOSTS)
        ),
        AsmodeeItaliaProvider(
            client(
                browser_fallback_hosts=(
                    AsmodeeItaliaProvider._HOSTS
                    | AsmodeeItaliaProvider._RULEBOOK_PAGE_HOSTS
                )
            )
        ),
        PendragonItaliaProvider(
            client(browser_fallback_hosts=PendragonItaliaProvider._HOSTS)
        ),
        MsEdizioniProvider(
            client(browser_fallback_hosts=MsEdizioniProvider._HOSTS)
        ),
    )


def production_community_rulebook_providers(
    *,
    timeout_seconds: float = 10.0,
    max_response_bytes: int = MAX_DISCOVERY_RESPONSE_BYTES,
    max_attempts: int = 2,
    min_interval_seconds: float = 1.0,
    rate_limiter: Callable[[str, float], None] | None = None,
) -> tuple[RulebookProvider, ...]:
    client = _production_client_factory(
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        max_attempts=max_attempts,
        min_interval_seconds=min_interval_seconds,
        rate_limiter=rate_limiter,
    )
    return (RuleBookOrgProvider(client()),)


def production_rulebook_providers(
    *,
    timeout_seconds: float = 10.0,
    max_response_bytes: int = MAX_DISCOVERY_RESPONSE_BYTES,
    max_attempts: int = 2,
    min_interval_seconds: float = 1.0,
    rate_limiter: Callable[[str, float], None] | None = None,
) -> tuple[RulebookProvider, ...]:
    return (
        *production_official_rulebook_providers(
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_attempts=max_attempts,
            min_interval_seconds=min_interval_seconds,
            rate_limiter=rate_limiter,
        ),
        *production_community_rulebook_providers(
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_attempts=max_attempts,
            min_interval_seconds=min_interval_seconds,
            rate_limiter=rate_limiter,
        ),
    )
