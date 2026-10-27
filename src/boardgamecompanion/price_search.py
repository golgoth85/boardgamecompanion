from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from boardgamecompanion.bgg_rulebook_search import GeminiBggFileProvider
from boardgamecompanion.gemini import validate_model_id
from boardgamecompanion.rulebooks import canonical_http_url

PRICE_GROUNDING_MODEL = "gemini-3.1-flash-lite"
MAX_OFFERS = 8
MAX_PRICE_EUR = 1000.0
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024

ITALIAN_SHOP_HOSTS = frozenset(
    {
        "amazon.it",
        "dungeondice.it",
        "egyp.it",
        "toyscenter.it",
        "lafeltrinelli.it",
        "ibs.it",
        "dragonstore.it",
        "libreriasemola.it",
        "giochistarter.it",
        "ebay.it",
        "fantasiastore.it",
        "player1.it",
        "baselunaitaly.it",
        "comicscorner.it",
        "boardgameuniverse.it",
        "ilcovodelnerd.com",
        "magicmerchant.it",
        "bottegaludica.it",
        "getyourfun.it",
        "eroidiarcadia.it",
    }
)
_AVAILABILITY = {"in_stock", "out_of_stock", "unknown"}


class PriceSearchError(RuntimeError):
    pass


def _api_error_message(response: httpx.Response) -> str | None:
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return None
    message = error.get("message") if isinstance(error, dict) else None
    if not isinstance(message, str) or not message.strip():
        return None
    return " ".join(message.split())[:300]


_ITALIAN_TITLE_MARKER = re.compile(r"\b(il|gli|degli|della|delle|dei|del)\b", re.IGNORECASE)


def shop_search_title(title: str, alternate_titles: tuple[str, ...] | list[str] = ()) -> str:
    return next((item for item in alternate_titles if _ITALIAN_TITLE_MARKER.search(item)), title)


def shop_host(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    for known in ITALIAN_SHOP_HOSTS:
        if host == known or host.endswith(f".{known}"):
            return known
    return None


def _grounding(first: dict[str, Any]) -> tuple[set[str], set[str]]:
    metadata = first.get("groundingMetadata")
    chunks = metadata.get("groundingChunks") if isinstance(metadata, dict) else None
    uris: set[str] = set()
    domains: set[str] = set()
    if not isinstance(chunks, list):
        return uris, domains
    for chunk in chunks:
        web = chunk.get("web") if isinstance(chunk, dict) else None
        if not isinstance(web, dict):
            continue
        uri = web.get("uri")
        if isinstance(uri, str):
            try:
                uris.add(canonical_http_url(uri))
            except ValueError:
                pass
        title = web.get("title")
        if isinstance(title, str):
            known = shop_host(f"https://{title.strip().lower()}/")
            if known:
                domains.add(known)
    return uris, domains


def _json_from_text(text: str) -> Any:
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    return json.loads(cleaned)


def parse_offers(first_candidate: dict[str, Any]) -> list[dict[str, Any]]:
    content = first_candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        return []
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if len(texts) != 1:
        return []
    try:
        structured = _json_from_text(texts[0])
    except (TypeError, ValueError, RecursionError) as exc:
        raise PriceSearchError("Price search did not return the required JSON") from exc
    items = structured.get("offers") if isinstance(structured, dict) else None
    if not isinstance(items, list):
        raise PriceSearchError("Price search offers are invalid")

    grounded_uris, grounded_domains = _grounding(first_candidate)
    offers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            url = canonical_http_url(str(item.get("url") or ""))
        except ValueError:
            continue
        if urlsplit(url).scheme != "https":
            continue
        host = shop_host(url)
        if host is None or url in seen:
            continue
        if url not in grounded_uris and host not in grounded_domains:
            continue
        try:
            price = float(item.get("price_eur"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or not 0 < price < MAX_PRICE_EUR:
            continue
        availability = str(item.get("availability") or "unknown").strip().lower()
        seen.add(url)
        offers.append(
            {
                "shop": host,
                "url": url,
                "price_eur": round(price, 2),
                "availability": availability if availability in _AVAILABILITY else "unknown",
            }
        )
    offers.sort(key=lambda offer: offer["price_eur"])
    return offers[:MAX_OFFERS]


def best_offer(offers: list[dict[str, Any]]) -> dict[str, Any] | None:
    for offer in offers:
        if offer["availability"] != "out_of_stock":
            return offer
    return None


class GeminiPriceProvider:
    """Italian shop price discovery via grounded Google Search.

    Prices are indicative: an offer is kept only when its shop is on the curated
    Italian allowlist and appears in the Google grounding evidence.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = PRICE_GROUNDING_MODEL,
        timeout_seconds: float = 45.0,
        verify_tls: bool = True,
        client: httpx.Client | None = None,
        rate_limiter: Callable[[str, float], None] | None = None,
        min_interval_seconds: float = 8.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.model = validate_model_id(model)
        self.timeout_seconds = float(timeout_seconds)
        self.verify_tls = bool(verify_tls)
        self.client = client
        self.rate_limiter = rate_limiter
        self.min_interval_seconds = float(min_interval_seconds)
        self.sleep = sleep
        if not self.base_url.startswith("https://"):
            raise ValueError("Gemini URL must use https://")
        if not self.api_key:
            raise ValueError("Gemini API key is required")

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        path = f"/v1beta/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key}
        for attempt in (1, 2):
            if self.rate_limiter is not None:
                self.rate_limiter("gemini:price-search", self.min_interval_seconds)
            try:
                if self.client is not None:
                    response = self.client.post(
                        path, headers=headers, json=payload, timeout=self.timeout_seconds
                    )
                else:
                    with httpx.Client(
                        base_url=self.base_url,
                        timeout=self.timeout_seconds,
                        verify=self.verify_tls,
                    ) as client:
                        response = client.post(path, headers=headers, json=payload)
                response.raise_for_status()
                if len(response.content) > _MAX_RESPONSE_BYTES:
                    raise PriceSearchError("Price search response is too large")
                return response
            except httpx.HTTPStatusError as exc:
                response = exc.response
                if (
                    response.status_code == 429
                    and attempt == 1
                    and not GeminiBggFileProvider._has_zero_quota(response)
                ):
                    self.sleep(10.0)
                    continue
                diagnostic = GeminiBggFileProvider._quota_diagnostic(response)
                message = _api_error_message(response)
                if message:
                    diagnostic = f"{diagnostic}; {message}" if diagnostic else message
                suffix = f" ({diagnostic})" if diagnostic else ""
                raise PriceSearchError(
                    f"Price search failed with HTTP {response.status_code}{suffix}"
                ) from exc
            except httpx.HTTPError as exc:
                if attempt == 1:
                    self.sleep(2.0)
                    continue
                raise PriceSearchError("Price search endpoint is unreachable") from exc
        raise PriceSearchError("Price search exhausted retry budget")

    def search(self, *, title: str, year: int | None = None, alternate_titles: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        shops = ", ".join(sorted(ITALIAN_SHOP_HOSTS))
        prompt = (
            "Find the current selling price in Italy, in euro, of exactly one board game. "
            f"Title: {shop_search_title(title, alternate_titles)!r}. Year: {year!r}. "
            "Prefer the Italian edition when it exists. Use Google Search and only "
            f"report product pages from these Italian shops: {shops}. "
            "Report only prices actually shown for this exact product, never a bundle, "
            "expansion, accessory or other game. Return ONLY compact JSON with this exact "
            'shape: {"offers":[{"url":"https://...","price_eur":29.99,'
            '"availability":"in_stock|out_of_stock|unknown"}]}. '
            "Return an empty offers list when no verified price is found."
        )
        response = self._post(
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "tools": [{"googleSearch": {}}],
            }
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise PriceSearchError("Price search returned invalid JSON") from exc
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list) or not candidates:
            return []
        first = candidates[0]
        return parse_offers(first) if isinstance(first, dict) else []
