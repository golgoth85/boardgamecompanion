from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from boardgamecompanion.copies import PhysicalCopyStore, normalize_barcode
from boardgamecompanion.database import Database


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


class BarcodeResolver:
    def __init__(
        self,
        database: Database,
        *,
        product_lookup: BarcodeProductLookup | None = None,
        positive_cache_days: int = 30,
        negative_cache_days: int = 7,
    ) -> None:
        self.database = database
        self.product_lookup = product_lookup or UpcItemDbLookup()
        self.positive_cache_days = max(1, int(positive_cache_days))
        self.negative_cache_days = max(1, int(negative_cache_days))

    @staticmethod
    def _cache_key(barcode: str) -> str:
        return f"barcode_product_lookup:{barcode}"

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
            {"schema_version": 1, "product": product},
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
            title_score = _title_score(product_text, str(row["title"] or ""))
            original_score = _title_score(
                product_text,
                str(row["original_title"] or ""),
            )
            score = max(title_score, original_score)
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
        external_lookup = "cache" if cached else "upcitemdb"
        if not cached:
            try:
                product = self.product_lookup.lookup(normalized)
                self._write_cache(normalized, product)
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

        candidates = self._owned_candidates(product)
        best = candidates[0] if candidates else None
        second = candidates[1] if len(candidates) > 1 else None
        auto_match = None
        if best is not None:
            best_score = float(best["confidence"])
            margin = best_score - float(second["confidence"]) if second else best_score
            if best_score >= 0.82 and margin >= 0.08:
                auto_match = best

        return {
            **local,
            "resolution": "owned_game" if auto_match else "product_identified",
            "product": product,
            "auto_match": auto_match,
            "candidates": candidates,
            "external_lookup": external_lookup,
        }
