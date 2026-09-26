from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

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
        self._gate_lock = threading.Lock()
        self._last_request_at: float | None = None

    def _rate_gate(self) -> None:
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
        host = (urlsplit(canonical).hostname or "").lower()
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

    def get(
        self,
        url: str,
        *,
        allowed_hosts: Iterable[str],
        accepted_statuses: frozenset[int] = frozenset({200}),
    ) -> ProviderHttpResponse:
        hosts = frozenset(str(host).strip().lower() for host in allowed_hosts)
        if not hosts:
            raise ValueError("allowed_hosts must not be empty")
        current = self._validate_origin(url, hosts)
        redirects = 0
        attempt = 0

        while True:
            self._rate_gate()
            response: httpx.Response | None = None
            try:
                if self.client is not None:
                    response = self.client.get(
                        current,
                        headers={
                            "Accept": "text/html, application/json;q=0.9",
                            "Accept-Encoding": "identity",
                            "User-Agent": (
                                "BoardGameCompanion/0.1 rulebook-discovery"
                            ),
                        },
                        timeout=self.timeout_seconds,
                        follow_redirects=False,
                    )
                else:
                    with httpx.Client(
                        timeout=self.timeout_seconds,
                        follow_redirects=False,
                        trust_env=False,
                    ) as client:
                        response = client.get(
                            current,
                            headers={
                                "Accept": "text/html, application/json;q=0.9",
                                "Accept-Encoding": "identity",
                                "User-Agent": (
                                    "BoardGameCompanion/0.1 rulebook-discovery"
                                ),
                            },
                        )
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
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location or redirects >= MAX_DISCOVERY_REDIRECTS:
                    raise ProviderHttpError("Provider redirect is invalid or excessive")
                current = self._validate_origin(urljoin(current, location), hosts)
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

            content = response.content
            declared = response.headers.get("content-length", "").strip()
            if declared.isdigit() and int(declared) > self.max_response_bytes:
                raise ProviderHttpError("Provider response exceeds the byte limit")
            if len(content) > self.max_response_bytes:
                raise ProviderHttpError("Provider response exceeds the byte limit")
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
    expected = tuple(_match_text(value) for value in names)
    return any(
        name == publisher or name in publisher or publisher in name
        for publisher in (_match_text(value) for value in query.publishers)
        if publisher
        for name in expected
        if name
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


class _OfficialPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._title_depth = 0
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.title_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "h1":
            self._title_depth += 1
        if tag.lower() == "a" and len(self.links) < MAX_DISCOVERY_RESULTS:
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


def _parse_official_page(content: bytes) -> _OfficialPageParser:
    try:
        text = content.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RulebookProviderError("Provider HTML is not valid UTF-8") from exc
    parser = _OfficialPageParser()
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
        publisher_verified = _publisher_matches(query, self._PUBLISHERS)
        if not publisher_verified:
            return ()

        seen_pages: set[str] = set()
        candidates: list[RulebookCandidate] = []
        for title in (query.title, query.original_title):
            if not title:
                continue
            page_url = f"{self._BASE}{quote(_slug(title), safe='-')}"
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

            seen_languages: set[str] = set()
            for href, label in page.links:
                absolute = urljoin(response.url, href)
                if (urlsplit(absolute).hostname or "").lower() not in self._PDF_HOSTS:
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
                        title=f"{page.title} — Rules",
                        bgg_id=query.bgg_id,
                        game_title=page.title,
                        year=query.year,
                        publisher="Repos Production",
                        metadata={
                            "official_page": response.url,
                            "identity_evidence": [
                                "official_page_title_exact",
                                "catalog_publisher_match",
                                "catalog_bgg_id",
                            ],
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
    _PDF_HOSTS = frozenset({"cdn.svc.asmodee.net", "www.asmodee.it", "asmodee.it"})

    def __init__(self, http: ProviderHttpClient | None = None):
        self.http = http or ProviderHttpClient()

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        publisher_verified = _publisher_matches(query, self._PUBLISHERS)
        page_url = f"{self._BASE}{quote(_slug(query.title), safe='-')}/"
        response = self.http.get(
            page_url,
            allowed_hosts=self._HOSTS,
            accepted_statuses=frozenset({200, 404}),
        )
        if response.status_code == 404:
            return ()
        page = _parse_official_page(response.content)
        if not _title_matches(query, page.title):
            return ()

        candidates: list[RulebookCandidate] = []
        for href, label in page.links:
            if "regolamento" not in _match_text(label):
                continue
            absolute = urljoin(response.url, href)
            if (urlsplit(absolute).hostname or "").lower() not in self._PDF_HOSTS:
                continue
            if not urlsplit(absolute).path.casefold().endswith(".pdf"):
                continue
            candidates.append(
                RulebookCandidate(
                    provider=self.name,
                    source_kind=RulebookSource.OFFICIAL_LOCALIZER,
                    url=absolute,
                    language="it",
                    document_type="rulebook",
                    official=True,
                    confidence=100 if publisher_verified else 94,
                    title=f"{page.title} — Regolamento italiano",
                    bgg_id=query.bgg_id if publisher_verified else None,
                    game_title=page.title,
                    year=query.year,
                    publisher="Asmodee Italia",
                    metadata={
                        "official_page": response.url,
                        "identity_evidence": (
                            [
                                "official_page_title_exact",
                                "catalog_publisher_match",
                                "catalog_bgg_id",
                            ]
                            if publisher_verified
                            else ["official_page_title_exact"]
                        ),
                        "catalog_item_type": query.item_type,
                    },
                )
            )
        return tuple(candidates[:MAX_DISCOVERY_RESULTS])


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


def production_rulebook_providers(
    *,
    timeout_seconds: float = 10.0,
    max_response_bytes: int = MAX_DISCOVERY_RESPONSE_BYTES,
    max_attempts: int = 2,
    min_interval_seconds: float = 1.0,
) -> tuple[RulebookProvider, ...]:
    def client() -> ProviderHttpClient:
        return ProviderHttpClient(
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_attempts=max_attempts,
            min_interval_seconds=min_interval_seconds,
        )

    return (
        ReposProductionProvider(client()),
        AsmodeeItaliaProvider(client()),
        RuleBookOrgProvider(client()),
    )
