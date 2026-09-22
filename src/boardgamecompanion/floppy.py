from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from boardgamecompanion.database import Database


class FloppyError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        kind: str = "request_error",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind


@dataclass(frozen=True)
class FloppyConfig:
    base_url: str
    api_key: str
    timeout_seconds: float = 8.0
    verify_tls: bool = True

    @property
    def normalized_url(self) -> str:
        return self.base_url.rstrip("/")


class FloppyClient:
    def __init__(
        self,
        config: FloppyConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport

    def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        params: dict[str, Any] | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["X-API-Key"] = self.config.api_key

        url = f"{self.config.normalized_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_tls,
                transport=self._transport,
                follow_redirects=True,
            ) as client:
                response = client.request(method, url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise FloppyError("Floppy request timed out", kind="timeout") from exc
        except httpx.RequestError as exc:
            raise FloppyError(f"Cannot reach Floppy: {exc}", kind="unreachable") from exc

        if response.status_code >= 400:
            detail = None
            try:
                body = response.json()
                if isinstance(body, dict):
                    detail = body.get("detail") or body.get("error")
            except ValueError:
                pass
            message = detail or f"Floppy returned HTTP {response.status_code}"
            kind = "authentication" if response.status_code in {401, 403} else "http_error"
            raise FloppyError(
                str(message),
                status_code=response.status_code,
                kind=kind,
            )

        if response.status_code == 204 or not response.content:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise FloppyError("Floppy returned a non-JSON response", kind="invalid_response") from exc

    def info(self) -> dict[str, Any]:
        body = self._request("GET", "/api/v1/info/", authenticated=False)
        return body if isinstance(body, dict) else {"value": body}

    def boardgames_page(self, *, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        body = self._request(
            "GET",
            "/api/v1/media/boardgame/",
            params={"limit": limit, "offset": offset},
        )
        if isinstance(body, list):
            return {"results": body, "pagination": {"total": len(body)}}
        if not isinstance(body, dict):
            raise FloppyError("Unexpected board-game list response", kind="invalid_response")
        return body

    def boardgames(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        offset = 0
        limit = 200

        while True:
            page = self.boardgames_page(limit=limit, offset=offset)
            rows = _extract_results(page)
            results.extend(row for row in rows if isinstance(row, dict))

            pagination = page.get("pagination") if isinstance(page, dict) else None
            total = pagination.get("total") if isinstance(pagination, dict) else None
            if isinstance(total, int) and len(results) >= total:
                break
            if len(rows) < limit:
                break
            offset += len(rows)
            if offset > 100_000:
                raise FloppyError("Floppy pagination did not terminate", kind="invalid_response")

        return results

    def schema_capabilities(self) -> dict[str, Any]:
        try:
            schema = self._request("GET", "/api/schema/", authenticated=True)
        except FloppyError as exc:
            return {
                "available": False,
                "media_write": False,
                "collection_write": False,
                "error": str(exc),
            }

        paths = schema.get("paths", {}) if isinstance(schema, dict) else {}
        media_write = False
        collection_write = False

        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            normalized = path.rstrip("/")
            if (
                normalized.endswith("/media/{media_type}/{source}/{media_id}")
                and "post" in methods
            ):
                media_write = True
            if normalized.endswith("/collection") and "post" in methods:
                collection_write = True

        return {
            "available": isinstance(schema, dict),
            "media_write": media_write,
            "collection_write": collection_write,
            "write_contract_ready": media_write and collection_write,
        }


def _extract_results(body: dict[str, Any]) -> list[Any]:
    for key in ("results", "items", "data"):
        value = body.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_title(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return re.sub(r"\s+", " ", text)


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _remote_bgg_id(item: dict[str, Any]) -> int | None:
    ids = item.get("ids")
    if isinstance(ids, dict):
        for key in ("bgg", "boardgamegeek"):
            value = _as_int(ids.get(key))
            if value is not None:
                return value

    source = str(item.get("source") or "").lower()
    media_id = _as_int(item.get("media_id"))
    if source in {"bgg", "boardgamegeek", "manual"} and media_id is not None:
        return media_id

    for key in ("bgg_id", "bggid", "boardgamegeek_id"):
        value = _as_int(item.get(key))
        if value is not None:
            return value
    return None


def _remote_year(item: dict[str, Any]) -> int | None:
    for key in ("year", "release_year", "year_published", "yearpublished"):
        value = _as_int(item.get(key))
        if value is not None:
            return value

    release_date = item.get("release_date")
    if isinstance(release_date, str) and len(release_date) >= 4:
        return _as_int(release_date[:4])
    return None


def _remote_title(item: dict[str, Any]) -> str:
    for key in ("title", "name", "original_title"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def local_owned_games(database: Database) -> list[dict[str, Any]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT g.bgg_id, g.title, g.original_title, g.year_published,
                   g.item_type, c.coll_id, c.own
            FROM board_games g
            JOIN collection_entries c ON c.board_game_id = g.id
            WHERE c.own = 1
            ORDER BY g.title COLLATE NOCASE, g.bgg_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def build_sync_preview(
    local_games: Iterable[dict[str, Any]],
    remote_games: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    local = list(local_games)
    remote = list(remote_games)
    by_bgg: dict[int, list[dict[str, Any]]] = {}
    by_title_year: dict[tuple[str, int | None], list[dict[str, Any]]] = {}

    for item in remote:
        bgg_id = _remote_bgg_id(item)
        if bgg_id is not None:
            by_bgg.setdefault(bgg_id, []).append(item)

        title = _normalize_title(_remote_title(item))
        if title:
            by_title_year.setdefault((title, _remote_year(item)), []).append(item)

    matches: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    for local_item in local:
        bgg_id = int(local_item["bgg_id"])
        exact = by_bgg.get(bgg_id, [])
        base = {
            "bgg_id": bgg_id,
            "title": local_item["title"],
            "year_published": local_item.get("year_published"),
            "item_type": local_item.get("item_type"),
        }

        if len(exact) == 1:
            item = exact[0]
            matches.append(
                {
                    **base,
                    "match_method": "bgg_id",
                    "remote": _remote_identity(item),
                }
            )
            continue
        if len(exact) > 1:
            ambiguous.append(
                {
                    **base,
                    "reason": "duplicate_bgg_id",
                    "candidates": [_remote_identity(item) for item in exact],
                }
            )
            continue

        key = (_normalize_title(local_item["title"]), local_item.get("year_published"))
        fallback = by_title_year.get(key, [])
        if len(fallback) == 1:
            matches.append(
                {
                    **base,
                    "match_method": "title_year",
                    "remote": _remote_identity(fallback[0]),
                }
            )
        elif len(fallback) > 1:
            ambiguous.append(
                {
                    **base,
                    "reason": "duplicate_title_year",
                    "candidates": [_remote_identity(item) for item in fallback],
                }
            )
        else:
            missing.append(base)

    exact_count = sum(item["match_method"] == "bgg_id" for item in matches)
    fallback_count = sum(item["match_method"] == "title_year" for item in matches)

    return {
        "local_owned": len(local),
        "remote_boardgames": len(remote),
        "matched": len(matches),
        "matched_by_bgg_id": exact_count,
        "matched_by_title_year": fallback_count,
        "missing_in_floppy": len(missing),
        "ambiguous": len(ambiguous),
        "matches": matches,
        "missing": missing,
        "ambiguous_items": ambiguous,
    }


def _remote_identity(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _remote_title(item),
        "year": _remote_year(item),
        "source": item.get("source"),
        "media_id": item.get("media_id"),
        "bgg_id": _remote_bgg_id(item),
        "item_id": item.get("item_id") or item.get("id"),
    }
