from __future__ import annotations

import json
import re
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from boardgamecompanion.gemini import validate_model_id
from boardgamecompanion.rulebooks import (
    RulebookCandidate,
    RulebookProviderError,
    RulebookQuery,
    RulebookSource,
    canonical_http_url,
)

_BGG_FILEPAGE_RE = re.compile(r"^/filepage/[0-9]+(?:/[^?#]*)?$")
_BGG_FILE_DOWNLOAD_PREFIX = "/file/download/"
_BGG_S3_PREFIX = "/geekdo-files.com/"
_BGG_HOSTS = frozenset({"boardgamegeek.com", "www.boardgamegeek.com"})
_ALLOWED_DOWNLOAD_HOSTS = frozenset(
    {
        "boardgamegeek.com",
        "www.boardgamegeek.com",
        "s3.amazonaws.com",
        "cdn.1j1ju.com",
    }
)
_MAX_RESULTS = 6
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024

# BGG grounding is pinned independently from the app's primary RAG model.
# This exact API identifier has been verified for Google Search grounding.
BGG_GROUNDING_MODEL = "gemini-3.5-flash-lite"


def _language_from(value: object, title: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"it", "ita", "italian", "italiano", "italiana"}:
        return "it"
    if raw in {"en", "eng", "english"}:
        return "en"
    normalized = " ".join(title.casefold().split())
    if any(token in normalized for token in ("italian", "italiano", "italiana", "regolamento", " ita ")):
        return "it"
    if any(token in normalized for token in ("english", "rulebook", "rules", " eng ")):
        return "en"
    return "und"


def _canonical_grounded_urls(first_candidate: dict[str, Any]) -> set[str]:
    metadata = first_candidate.get("groundingMetadata")
    if not isinstance(metadata, dict):
        return set()
    chunks = metadata.get("groundingChunks")
    if not isinstance(chunks, list):
        return set()
    urls: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web")
        if not isinstance(web, dict):
            continue
        uri = web.get("uri")
        if not isinstance(uri, str):
            continue
        try:
            urls.add(canonical_http_url(uri))
        except ValueError:
            continue
    return urls


def _is_bgg_filepage(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and (parts.hostname or "").lower() in _BGG_HOSTS
        and bool(_BGG_FILEPAGE_RE.fullmatch(parts.path))
    )


def _is_allowed_download(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or host not in _ALLOWED_DOWNLOAD_HOSTS:
        return False
    if host in _BGG_HOSTS:
        return parts.path.startswith(_BGG_FILE_DOWNLOAD_PREFIX)
    if host == "s3.amazonaws.com":
        return parts.path.startswith(_BGG_S3_PREFIX)
    if host == "cdn.1j1ju.com":
        return parts.path.lower().endswith(".pdf")
    return False


class GeminiBggFileProvider:
    """Second-line BGG rulebook discovery via grounded Google Search.

    The model is used only to associate two URLs already present in Google
    grounding evidence: a BGG filepage and a fetchable transport URL. The
    provider never trusts an ungrounded URL and every candidate is community
    sourced, so the existing review gate remains mandatory.
    """

    name = "bgg_google_search"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 20.0,
        verify_tls: bool = True,
        client: httpx.Client | None = None,
        rate_limiter: Callable[[str, float], None] | None = None,
        min_interval_seconds: float = 8.0,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.model = validate_model_id(model)
        self.api_key = str(api_key or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        self.verify_tls = bool(verify_tls)
        self.client = client
        self.rate_limiter = rate_limiter
        self.min_interval_seconds = float(min_interval_seconds)
        self.max_attempts = int(max_attempts)
        self.sleep = sleep
        if not self.base_url.startswith("https://"):
            raise ValueError("Gemini URL must use https://")
        if not self.api_key:
            raise ValueError("Gemini API key is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be non-negative")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("max_attempts must be 1..5")

    @staticmethod
    def _retry_delay(response: httpx.Response, *, fallback: float) -> float:
        delay = float(fallback)

        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            details = error.get("details") if isinstance(error, dict) else None
            if isinstance(details, list):
                for item in details:
                    if not isinstance(item, dict):
                        continue
                    type_name = str(item.get("@type") or "")
                    if not type_name.endswith("RetryInfo"):
                        continue
                    raw = item.get("retryDelay")
                    if not isinstance(raw, str):
                        continue
                    match = re.fullmatch(r"([0-9]+(?:\\.[0-9]+)?)s", raw.strip())
                    if match:
                        delay = max(delay, float(match.group(1)))

        return min(60.0, delay)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        path = f"/v1beta/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key}
        for attempt in range(1, self.max_attempts + 1):
            if self.rate_limiter is not None:
                self.rate_limiter("gemini:bgg-google-search", self.min_interval_seconds)
            try:
                if self.client is not None:
                    response = self.client.post(
                        path,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout_seconds,
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
                    raise RulebookProviderError("BGG grounded search response is too large")
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429 and attempt < self.max_attempts:
                    retry_after = self._retry_delay(
                        exc.response,
                        fallback=min(20.0, 10.0 * attempt),
                    )
                    self.sleep(retry_after)
                    continue
                raise RulebookProviderError(
                    f"BGG grounded search failed with HTTP {status}"
                ) from exc
            except httpx.HTTPError as exc:
                if attempt < self.max_attempts:
                    self.sleep(min(2.0 * attempt, 5.0))
                    continue
                raise RulebookProviderError(
                    "BGG grounded search endpoint is unreachable"
                ) from exc
        raise RulebookProviderError("BGG grounded search exhausted retry budget")

    def discover(self, query: RulebookQuery):
        prompt = (
            "Find rulebook files for exactly one BoardGameGeek game. "
            f"BGG ID: {query.bgg_id}. Title: {query.title!r}. "
            f"Original title: {query.original_title!r}. Year: {query.year!r}. "
            "Use Google Search. Prefer Italian, then English. Search specifically "
            "for BoardGameGeek /filepage/ results and a fetchable PDF transport "
            "for the same file. Accepted transports are BoardGameGeek /file/download/, "
            "s3.amazonaws.com/geekdo-files.com, or cdn.1j1ju.com PDF mirrors. "
            "Return ONLY compact JSON with this exact shape: "
            '{"items":[{"source_url":"https://boardgamegeek.com/filepage/...",'
            '"download_url":"https://...","language":"it|en|und","title":"..."}]}. '
            "Return at most 6 items and return an empty items list when no verified "
            "pair is found."
        )
        response = self._post(
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "tools": [{"googleSearch": {}}],
            }
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RulebookProviderError("BGG grounded search returned invalid JSON") from exc
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list) or not candidates:
            return ()
        first = candidates[0]
        if not isinstance(first, dict):
            return ()
        content = first.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            return ()
        text_parts = [
            part.get("text")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        if len(text_parts) != 1:
            return ()
        try:
            structured = json.loads(text_parts[0])
        except (TypeError, ValueError, RecursionError) as exc:
            raise RulebookProviderError(
                "BGG grounded search did not return the required JSON shape"
            ) from exc
        items = structured.get("items") if isinstance(structured, dict) else None
        if not isinstance(items, list):
            raise RulebookProviderError("BGG grounded search items are invalid")

        grounded = _canonical_grounded_urls(first)
        results: list[RulebookCandidate] = []
        seen: set[tuple[str, str]] = set()
        for item in items[:_MAX_RESULTS]:
            if not isinstance(item, dict):
                continue
            raw_source = item.get("source_url")
            raw_download = item.get("download_url")
            if not isinstance(raw_source, str) or not isinstance(raw_download, str):
                continue
            try:
                source_url = canonical_http_url(raw_source)
                download_url = canonical_http_url(raw_download)
            except ValueError:
                continue
            if source_url not in grounded or download_url not in grounded:
                continue
            if not _is_bgg_filepage(source_url) or not _is_allowed_download(download_url):
                continue
            title = str(item.get("title") or "BoardGameGeek rulebook").strip()[:500]
            language = _language_from(item.get("language"), title)
            key = (source_url, download_url)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                RulebookCandidate(
                    provider=self.name,
                    source_kind=RulebookSource.COMMUNITY,
                    url=download_url,
                    language=language,
                    document_type="rulebook",
                    official=False,
                    confidence=70,
                    title=title,
                    bgg_id=query.bgg_id,
                    game_title=query.title,
                    year=query.year,
                    metadata={
                        "bgg_filepage": source_url,
                        "transport_url": download_url,
                        "identity_evidence": [
                            "requested_bgg_id",
                            "google_grounded_bgg_filepage",
                            "google_grounded_transport",
                        ],
                        "catalog_item_type": query.item_type,
                    },
                )
            )
        return tuple(results)
