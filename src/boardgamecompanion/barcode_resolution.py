from __future__ import annotations

import json
import re
import unicodedata
from html import unescape
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx

from boardgamecompanion.copies import PhysicalCopyStore, normalize_barcode
from boardgamecompanion.database import Database
from boardgamecompanion.title_search import game_title_terms


class BarcodeProductLookupError(RuntimeError):
    pass


class BarcodeProductLookup(Protocol):
    def lookup(self, barcode: str) -> dict[str, Any] | None: ...


_GENERIC_PRODUCT_TOKENS = {
    "board",
    "game",
    "games",
    "tabletop",
    "edition",
    "edizione",
    "gioco",
    "giochi",
    "the",
    "a",
    "an",
    "by",
    "from",
    "new",
}


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    return re.sub(r"\s+", " ", text).strip()


def _meaningful_tokens(value: object) -> tuple[str, ...]:
    return tuple(
        token
        for token in _normalize_text(value).split()
        if len(token) >= 2 and token not in _GENERIC_PRODUCT_TOKENS
    )


def _title_score(product_text: str, candidate_title: str) -> float:
    product_norm = _normalize_text(product_text)
    candidate_norm = _normalize_text(candidate_title)
    if not product_norm or not candidate_norm:
        return 0.0

    candidate_tokens = _meaningful_tokens(candidate_title)
    product_tokens = set(_meaningful_tokens(product_text))
    if not candidate_tokens:
        return 0.0

    coverage = sum(1 for token in candidate_tokens if token in product_tokens) / len(
        candidate_tokens
    )
    sequence = SequenceMatcher(None, candidate_norm, product_norm).ratio()
    phrase = 0.0
    if len(candidate_norm) >= 4 and re.search(
        rf"(^|\s){re.escape(candidate_norm)}($|\s)",
        product_norm,
    ):
        phrase = 0.98
    elif candidate_norm in product_norm:
        phrase = 0.92

    return round(max(phrase, (0.72 * coverage) + (0.28 * sequence)), 4)


_VERIFIED_BARCODE_PRODUCTS: dict[str, dict[str, Any]] = {
    "3558380049463": {
        "barcode": "3558380049463",
        "bgg_id": 184151,
        "title": "La Leggenda dei Cinque Anelli: Il Gioco di Carte",
        "brand": "Asmodee Italia",
        "category": "Board Games",
        "description": "Legend of the Five Rings: The Card Game",
        "images": [],
        "source": "verified_catalog",
        "source_url": (
            "https://www.uplay.it/it/"
            "gioco-da-tavolo-la-leggenda-dei-cinque-anelli--il-gioco-di-carte.html"
        ),
    },
}


class VerifiedBarcodeLookup:
    """Small audited GTIN catalog for products with a verified primary source."""

    def lookup(self, barcode: str) -> dict[str, Any] | None:
        normalized = normalize_barcode(barcode)
        if normalized is None:
            return None
        product = _VERIFIED_BARCODE_PRODUCTS.get(normalized)
        return dict(product) if product is not None else None


class UpcItemDbLookup:
    endpoint = "https://api.upcitemdb.com/prod/trial/lookup"

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = max(2.0, min(float(timeout_seconds), 20.0))

    def lookup(self, barcode: str) -> dict[str, Any] | None:
        normalized = normalize_barcode(barcode)
        if normalized is None or not normalized.isdigit():
            return None
        url = f"{self.endpoint}?{urlencode({'upc': normalized})}"
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "BoardGameCompanion/0.1 barcode-resolver",
                },
                follow_redirects=True,
            ) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            raise BarcodeProductLookupError(
                f"UPCitemdb lookup failed: {exc}"
            ) from exc

        if response.status_code == 404:
            return None
        if response.status_code == 429:
            raise BarcodeProductLookupError("UPCitemdb rate limit reached")
        if response.status_code >= 400:
            raise BarcodeProductLookupError(
                f"UPCitemdb HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise BarcodeProductLookupError("UPCitemdb returned invalid JSON") from exc

        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            return None
        item = items[0] if isinstance(items[0], dict) else {}
        return {
            "barcode": normalized,
            "title": str(item.get("title") or "").strip() or None,
            "brand": str(item.get("brand") or "").strip() or None,
            "category": str(item.get("category") or "").strip() or None,
            "description": str(item.get("description") or "").strip() or None,
            "images": [
                str(value)
                for value in (item.get("images") or [])
                if str(value).strip()
            ][:4],
            "source": "upcitemdb",
        }


class UplayBarcodeLookup:
    """Board-game-specific public-web fallback for Italian/European GTINs.

    Uplay product pages expose exact BARCODE fields, but no single search surface
    is reliable for server-side barcode discovery. Use a bounded sequence of the
    public Uplay search plus public search indexes, then trust a result only after
    fetching an allowlisted Uplay product page and verifying the barcode verbatim.
    """

    search_endpoints = (
        ("https://www.uplay.it/it/search", "query"),
        ("https://www.google.com/search", "q"),
        ("https://html.duckduckgo.com/html/", "q"),
    )
    allowed_hosts = {"uplay.it", "www.uplay.it"}
    duckduckgo_hosts = {"duckduckgo.com", "html.duckduckgo.com"}
    google_hosts = {"google.com", "www.google.com"}
    _href_pattern = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)
    _tag_pattern = re.compile(r"<[^>]+>")
    _h1_pattern = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        transport: Any | None = None,
    ) -> None:
        self.timeout_seconds = max(2.0, min(float(timeout_seconds), 20.0))
        self.transport = transport

    @classmethod
    def _text(cls, html: str) -> str:
        value = cls._tag_pattern.sub(" ", html)
        value = unescape(value)
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def _unwrap_search_url(cls, base_url: str, raw_href: str) -> str | None:
        href = unescape(raw_href)
        candidate = urljoin(base_url, href)
        parsed = urlparse(candidate)
        hostname = (parsed.hostname or "").casefold()
        if hostname in cls.duckduckgo_hosts:
            redirect = parse_qs(parsed.query).get("uddg", [])
            if not redirect:
                return None
            candidate = redirect[0]
            parsed = urlparse(candidate)
            hostname = (parsed.hostname or "").casefold()
        elif hostname in cls.google_hosts and parsed.path == "/url":
            query = parse_qs(parsed.query)
            redirect = query.get("q", []) or query.get("url", [])
            if not redirect:
                return None
            candidate = redirect[0]
            parsed = urlparse(candidate)
            hostname = (parsed.hostname or "").casefold()

        if parsed.scheme not in {"http", "https"}:
            return None
        if hostname not in cls.allowed_hosts:
            return None
        if not parsed.path.startswith("/it/"):
            return None
        if "gioco-da-tavolo-" not in parsed.path or not parsed.path.endswith(".html"):
            return None
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    @classmethod
    def _product_urls(cls, base_url: str, html: str) -> list[str]:
        urls: list[str] = []
        for raw_href in cls._href_pattern.findall(html):
            normalized = cls._unwrap_search_url(base_url, raw_href)
            if normalized is None or normalized in urls:
                continue
            urls.append(normalized)
            if len(urls) >= 5:
                break
        return urls

    @classmethod
    def _parse_product_page(
        cls,
        html: str,
        barcode: str,
        *,
        source_url: str,
    ) -> dict[str, Any] | None:
        text = cls._text(html)
        if not re.search(
            rf"\bBARCODE\b[\s:|]*{re.escape(barcode)}\b",
            text,
            re.IGNORECASE,
        ):
            return None

        title_match = cls._h1_pattern.search(html)
        title = cls._text(title_match.group(1)) if title_match else ""
        if not title:
            return None

        aliases_match = re.search(
            r"Nomi alternativi\s*:\s*(.*?)\s*BARCODE\s*:",
            text,
            re.IGNORECASE,
        )
        aliases = aliases_match.group(1).strip() if aliases_match else ""
        publisher_match = re.search(
            r"Editore\s*:\s*([^|]{1,120}?)(?:\s{2,}|La |Prezzo|Disponibile|$)",
            text,
            re.IGNORECASE,
        )
        publisher = publisher_match.group(1).strip() if publisher_match else None

        return {
            "barcode": barcode,
            "title": title,
            "brand": publisher,
            "category": "Board Games",
            "description": aliases or None,
            "images": [],
            "source": "uplay",
            "source_url": source_url,
        }

    def lookup(self, barcode: str) -> dict[str, Any] | None:
        normalized = normalize_barcode(barcode)
        if normalized is None or not normalized.isdigit():
            return None

        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "Mozilla/5.0 (compatible; BoardGameCompanion/0.1; "
                "+self-hosted-barcode-resolver)"
            ),
        }
        public_queries = (
            f'"{normalized}" site:uplay.it/it/gioco-da-tavolo',
            f"{normalized} uplay gioco da tavolo",
        )
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers=headers,
                follow_redirects=True,
                transport=self.transport,
            ) as client:
                product_urls: list[str] = []
                for endpoint, parameter in self.search_endpoints:
                    queries = (
                        (normalized,)
                        if endpoint.startswith("https://www.uplay.it/")
                        else public_queries
                    )
                    for query in queries:
                        response = client.get(endpoint, params={parameter: query})
                        if response.status_code >= 400:
                            continue
                        for product_url in self._product_urls(
                            str(response.url),
                            response.text,
                        ):
                            if product_url not in product_urls:
                                product_urls.append(product_url)
                            if len(product_urls) >= 5:
                                break
                        if product_urls:
                            break
                    if product_urls:
                        break

                for product_url in product_urls:
                    page = client.get(product_url)
                    if page.status_code >= 400:
                        continue
                    product = self._parse_product_page(
                        page.text,
                        normalized,
                        source_url=product_url,
                    )
                    if product is not None:
                        return product
        except BarcodeProductLookupError:
            raise
        except httpx.HTTPError as exc:
            raise BarcodeProductLookupError(
                f"public board-game barcode lookup failed: {exc}"
            ) from exc
        return None

class FallbackBarcodeLookup:
    def __init__(self, *lookups: BarcodeProductLookup) -> None:
        if not lookups:
            raise ValueError("at least one barcode lookup is required")
        self.lookups = lookups

    def lookup_all(self, barcode: str) -> list[dict[str, Any]]:
        errors: list[str] = []
        completed_provider = False
        products: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for lookup in self.lookups:
            try:
                product = lookup.lookup(barcode)
            except BarcodeProductLookupError as exc:
                errors.append(str(exc))
                continue
            completed_provider = True
            if product is None:
                continue
            key = (
                str(product.get("source") or ""),
                str(product.get("title") or ""),
                str(product.get("source_url") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            products.append(product)

        if not completed_provider and errors:
            raise BarcodeProductLookupError("; ".join(errors))
        return products

    def lookup(self, barcode: str) -> dict[str, Any] | None:
        products = self.lookup_all(barcode)
        return products[0] if products else None


class BarcodeResolver:
    def __init__(
        self,
        database: Database,
        *,
        product_lookup: BarcodeProductLookup | None = None,
        positive_cache_days: int = 30,
        negative_cache_days: int = 1,
    ) -> None:
        self.database = database
        self.product_lookup = product_lookup or FallbackBarcodeLookup(
            VerifiedBarcodeLookup(),
            UpcItemDbLookup(),
            UplayBarcodeLookup(),
        )
        self.positive_cache_days = max(1, int(positive_cache_days))
        self.negative_cache_days = max(1, int(negative_cache_days))

    @staticmethod
    def _cache_key(barcode: str) -> str:
        return f"barcode_product_lookup:v6:{barcode}"

    def _read_cache(self, barcode: str) -> tuple[bool, dict[str, Any] | None]:
        key = self._cache_key(barcode)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value,updated_at FROM app_settings WHERE key=?",
                (key,),
            ).fetchone()
        if row is None:
            return False, None
        try:
            payload = json.loads(row["value"])
            updated_at = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
        except (ValueError, TypeError, json.JSONDecodeError):
            return False, None
        product = payload.get("product") if isinstance(payload, dict) else None
        ttl_days = self.positive_cache_days if product else self.negative_cache_days
        if datetime.now(UTC) - updated_at.astimezone(UTC) > timedelta(days=ttl_days):
            return False, None
        return True, product if isinstance(product, dict) else None

    def _write_cache(self, barcode: str, product: dict[str, Any] | None) -> None:
        now = datetime.now(UTC).isoformat()
        value = json.dumps(
            {"schema_version": 6, "product": product},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO app_settings(key,value,sensitive,updated_at)
                VALUES(?,?,0,?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    sensitive=0,
                    updated_at=excluded.updated_at
                """,
                (self._cache_key(barcode), value, now),
            )

    def _verified_candidate(
        self,
        product: dict[str, Any],
    ) -> dict[str, Any] | None:
        raw_bgg_id = product.get("bgg_id")
        if isinstance(raw_bgg_id, bool):
            return None
        try:
            bgg_id = int(raw_bgg_id)
        except (TypeError, ValueError):
            return None
        if bgg_id < 1:
            return None

        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT g.bgg_id,g.title,g.original_title,g.year_published,
                       e.cover_url,e.metadata_json,
                       GROUP_CONCAT(DISTINCT c.version_publishers) AS publishers
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
                WHERE g.bgg_id=?
                GROUP BY g.id
                """,
                (bgg_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "bgg_id": int(row["bgg_id"]),
            "title": str(row["title"]),
            "original_title": row["original_title"],
            "year_published": row["year_published"],
            "cover_url": row["cover_url"],
            "publishers": row["publishers"],
            "confidence": 1.0,
        }

    def _owned_candidates(self, product: dict[str, Any]) -> list[dict[str, Any]]:
        product_text = " ".join(
            str(product.get(key) or "")
            for key in ("title", "brand", "description")
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id,g.title,g.original_title,g.year_published,
                       e.cover_url,
                       GROUP_CONCAT(DISTINCT c.version_publishers) AS publishers
                FROM board_games g
                JOIN collection_entries c ON c.board_game_id=g.id
                LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
                WHERE COALESCE(c.own,0)=1
                GROUP BY g.id
                ORDER BY g.title COLLATE NOCASE
                """
            ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            terms = game_title_terms(
                title=row["title"],
                original_title=row["original_title"],
                metadata_json=row["metadata_json"],
            )
            score = max(
                (_title_score(product_text, term) for term in terms),
                default=0.0,
            )
            if score < 0.45:
                continue
            candidates.append(
                {
                    "bgg_id": int(row["bgg_id"]),
                    "title": str(row["title"]),
                    "original_title": row["original_title"],
                    "year_published": row["year_published"],
                    "cover_url": row["cover_url"],
                    "publishers": row["publishers"],
                    "confidence": round(score, 3),
                }
            )
        candidates.sort(
            key=lambda item: (
                -float(item["confidence"]),
                str(item["title"]).casefold(),
            )
        )
        return candidates[:5]

    def _evaluate_product(
        self,
        product: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        verified_candidate = self._verified_candidate(product)
        if verified_candidate is not None:
            return [verified_candidate], verified_candidate

        candidates = self._owned_candidates(product)
        best = candidates[0] if candidates else None
        second = candidates[1] if len(candidates) > 1 else None
        auto_match = None
        if best is not None:
            best_score = float(best["confidence"])
            margin = (
                best_score - float(second["confidence"])
                if second
                else best_score
            )
            if best_score >= 0.82 and margin >= 0.08:
                auto_match = best
        return candidates, auto_match

    def _lookup_products(self, barcode: str) -> list[dict[str, Any]]:
        if isinstance(self.product_lookup, FallbackBarcodeLookup):
            return self.product_lookup.lookup_all(barcode)
        product = self.product_lookup.lookup(barcode)
        return [product] if product is not None else []

    def _choose_product(
        self,
        products: list[dict[str, Any]],
    ) -> tuple[
        dict[str, Any] | None,
        list[dict[str, Any]],
        dict[str, Any] | None,
    ]:
        best_product: dict[str, Any] | None = None
        best_candidates: list[dict[str, Any]] = []
        best_auto_match: dict[str, Any] | None = None
        best_rank: tuple[int, float, int, int] | None = None

        for index, product in enumerate(products):
            candidates, auto_match = self._evaluate_product(product)
            top_score = (
                float(auto_match["confidence"])
                if auto_match is not None
                else float(candidates[0]["confidence"])
                if candidates
                else 0.0
            )
            rank = (
                1 if auto_match is not None else 0,
                top_score,
                1 if str(product.get("source") or "") == "verified_catalog" else 0,
                -index,
            )
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_product = product
                best_candidates = candidates
                best_auto_match = auto_match

        return best_product, best_candidates, best_auto_match

    def lookup(self, barcode: str) -> dict[str, Any]:
        local = PhysicalCopyStore(self.database).lookup_barcode(barcode)
        if local["count"]:
            return {
                **local,
                "resolution": "local_copy",
                "product": None,
                "auto_match": None,
                "candidates": [],
                "external_lookup": "not_needed",
            }

        normalized = str(local["normalized"])
        if not normalized.isdigit() or len(normalized) not in {8, 12, 13, 14}:
            return {
                **local,
                "resolution": "unresolved",
                "product": None,
                "auto_match": None,
                "candidates": [],
                "external_lookup": "unsupported_barcode",
            }

        cached, product = self._read_cache(normalized)
        external_lookup = "cache" if cached else "providers"
        candidates: list[dict[str, Any]] = []
        auto_match: dict[str, Any] | None = None

        if cached:
            if product:
                candidates, auto_match = self._evaluate_product(product)
        else:
            try:
                products = self._lookup_products(normalized)
                product, candidates, auto_match = self._choose_product(products)
                self._write_cache(normalized, product)
                if product is not None:
                    external_lookup = str(product.get("source") or "providers")
            except BarcodeProductLookupError as exc:
                return {
                    **local,
                    "resolution": "unresolved",
                    "product": None,
                    "auto_match": None,
                    "candidates": [],
                    "external_lookup": "failed",
                    "external_error": str(exc),
                }

        if not product:
            return {
                **local,
                "resolution": "unresolved",
                "product": None,
                "auto_match": None,
                "candidates": [],
                "external_lookup": external_lookup,
            }

        return {
            **local,
            "resolution": "owned_game" if auto_match else "product_identified",
            "product": product,
            "auto_match": auto_match,
            "candidates": candidates,
            "external_lookup": external_lookup,
        }
