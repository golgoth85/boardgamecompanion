from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
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


class FloppyPlanChanged(RuntimeError):
    pass


@dataclass(frozen=True)
class FloppyConfig:
    base_url: str
    api_key: str
    timeout_seconds: float = 45.0
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
        json_body: dict[str, Any] | None = None,
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
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
        except httpx.TimeoutException as exc:
            raise FloppyError("Floppy request timed out", kind="timeout") from exc
        except httpx.RequestError as exc:
            raise FloppyError(f"Cannot reach Floppy: {exc}", kind="unreachable") from exc

        if response.status_code >= 400:
            detail = None
            errors = None
            try:
                body = response.json()
                if isinstance(body, dict):
                    detail = body.get("detail") or body.get("error")
                    errors = body.get("errors")
            except ValueError:
                pass
            message = detail or f"Floppy returned HTTP {response.status_code}"
            if errors:
                message = f"{message}: {errors}"
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
            raise FloppyError(
                "Floppy returned a non-JSON response",
                kind="invalid_response",
            ) from exc

    def info(self) -> dict[str, Any]:
        body = self._request("GET", "/api/v1/info/", authenticated=False)
        return body if isinstance(body, dict) else {"value": body}

    def boardgames_page(self, *, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        body = self._request(
            "GET",
            "/api/v1/media/boardgame/",
            params={"limit": limit, "offset": offset},
        )
        return _normalize_page(body, "board-game list")

    def boardgames(self) -> list[dict[str, Any]]:
        return self._all_pages(self.boardgames_page)

    def collection_page(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        item_media_type: str = "boardgame",
    ) -> dict[str, Any]:
        body = self._request(
            "GET",
            "/api/v1/collection/",
            params={
                "limit": limit,
                "offset": offset,
                "item_media_type": item_media_type,
            },
        )
        return _normalize_page(body, "collection list")

    def collection_entries(self) -> list[dict[str, Any]]:
        return self._all_pages(self.collection_page)

    def _all_pages(self, page_loader) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        offset = 0
        limit = 200

        while True:
            page = page_loader(limit=limit, offset=offset)
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
                raise FloppyError(
                    "Floppy pagination did not terminate",
                    kind="invalid_response",
                )

        return results

    def boardgame_bgg_detail(self, bgg_id: int) -> dict[str, Any] | None:
        try:
            body = self._request(
                "GET",
                f"/api/v1/media/boardgame/bgg/{int(bgg_id)}/",
            )
        except FloppyError as exc:
            if exc.status_code == 404:
                return None
            raise
        if not isinstance(body, dict):
            raise FloppyError(
                "Unexpected response while reading BGG board game detail",
                kind="invalid_response",
            )
        # Floppy also uses this endpoint as a live BGG provider lookup.
        # Provider-only results have id=null / tracked=false and are not yet
        # persisted media, so they must not be treated as existing items.
        if _remote_item_db_id(body) is None:
            return None
        return body

    def track_boardgame_bgg(self, bgg_id: int) -> dict[str, Any]:
        body = self._request(
            "POST",
            "/api/v1/media/boardgame/",
            json_body={
                "source": "bgg",
                "media_id": str(bgg_id),
                # Blank means a held/untracked row rather than Planning.
                "status": "",
                # Floppy board-game tracking requires an explicit progress value.
                "progress": 0,
            },
        )
        if not isinstance(body, dict):
            raise FloppyError(
                "Unexpected response while creating BGG board game",
                kind="invalid_response",
            )
        return body

    def track_boardgame_manual(self, title: str) -> dict[str, Any]:
        body = self._request(
            "POST",
            "/api/v1/media/boardgame/",
            json_body={
                "source": "manual",
                "title": title,
                # Blank means a held/untracked row rather than Planning.
                "status": "",
                # Floppy board-game tracking requires an explicit progress value.
                "progress": 0,
            },
        )
        if not isinstance(body, dict):
            raise FloppyError(
                "Unexpected response while creating manual board game",
                kind="invalid_response",
            )
        return body

    def add_collection_entry(
        self,
        *,
        item_db_id: int,
        purchase_price: float | None = None,
        purchase_location: str | None = None,
        collected_at: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"item_id": item_db_id}
        if purchase_price is not None:
            payload["purchase_price"] = purchase_price
        if purchase_location:
            payload["purchase_location"] = purchase_location
        if collected_at:
            payload["collected_at"] = collected_at

        body = self._request(
            "POST",
            "/api/v1/collection/",
            json_body=payload,
        )
        if not isinstance(body, dict):
            raise FloppyError(
                "Unexpected response while adding collection entry",
                kind="invalid_response",
            )
        return body

    def schema_capabilities(self) -> dict[str, Any]:
        try:
            schema = self._request("GET", "/api/schema/", authenticated=True)
        except FloppyError as exc:
            return {
                "available": False,
                "media_write": False,
                "collection_write": False,
                "write_contract_ready": False,
                "error": str(exc),
            }

        paths = schema.get("paths", {}) if isinstance(schema, dict) else {}
        media_write = False
        collection_write = False

        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            normalized = path.rstrip("/")
            if normalized.endswith("/media/{media_type}") and "post" in methods:
                media_write = True
            if normalized.endswith("/collection") and "post" in methods:
                collection_write = True

        return {
            "available": isinstance(schema, dict),
            "media_write": media_write,
            "collection_write": collection_write,
            "write_contract_ready": media_write and collection_write,
        }


def _normalize_page(body: Any, description: str) -> dict[str, Any]:
    if isinstance(body, list):
        return {"results": body, "pagination": {"total": len(body)}}
    if not isinstance(body, dict):
        raise FloppyError(
            f"Unexpected {description} response",
            kind="invalid_response",
        )
    return body


def _extract_results(body: dict[str, Any]) -> list[Any]:
    for key in ("results", "items", "data"):
        value = body.get(key)
        if isinstance(value, list):
            return value
    return []


def _nested_item(value: dict[str, Any]) -> dict[str, Any]:
    item = value.get("item")
    return item if isinstance(item, dict) else value


def _normalize_title(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = "".join(char.lower() if char.isalnum() else " " for char in text)
    return re.sub(r"\s+", " ", text).strip()


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _remote_source(value: dict[str, Any]) -> str:
    item = _nested_item(value)
    return str(item.get("source") or value.get("source") or "").lower()


def _remote_media_id(value: dict[str, Any]) -> str:
    item = _nested_item(value)
    raw = item.get("media_id")
    if raw is None:
        raw = value.get("media_id")
    return str(raw) if raw is not None else ""


def _remote_item_db_id(value: dict[str, Any]) -> int | None:
    # List/media rows expose the database Item.id as the top-level id while
    # collection rows also have a nested item but their top-level id belongs
    # to the collection entry. Direct media detail responses are flat and
    # expose Item.id as top-level id without a nested item.
    if isinstance(value.get("item"), dict):
        return _as_int(value.get("id"))
    return _as_int(value.get("item_db_id")) or _as_int(value.get("id"))


def _remote_bgg_id(value: dict[str, Any]) -> int | None:
    item = _nested_item(value)
    ids = item.get("ids")
    if isinstance(ids, dict):
        for key in ("bgg", "boardgamegeek"):
            parsed = _as_int(ids.get(key))
            if parsed is not None:
                return parsed

    source = _remote_source(value)
    media_id = _as_int(_remote_media_id(value))
    if source in {"bgg", "boardgamegeek"} and media_id is not None:
        return media_id

    for container in (item, value):
        for key in ("bgg_id", "bggid", "boardgamegeek_id"):
            parsed = _as_int(container.get(key))
            if parsed is not None:
                return parsed
    return None


def _remote_year(value: dict[str, Any]) -> int | None:
    item = _nested_item(value)
    for container in (item, value):
        for key in (
            "year",
            "release_year",
            "year_published",
            "yearpublished",
        ):
            parsed = _as_int(container.get(key))
            if parsed is not None:
                return parsed

        for key in ("release_date", "release_datetime"):
            release_date = container.get(key)
            if isinstance(release_date, str) and len(release_date) >= 4:
                parsed = _as_int(release_date[:4])
                if parsed is not None:
                    return parsed
    return None


def _remote_title(value: dict[str, Any]) -> str:
    item = _nested_item(value)
    for container in (item, value):
        for key in ("title", "name", "original_title"):
            title = container.get(key)
            if title:
                return str(title)
    return ""


def _remote_coordinate(value: dict[str, Any]) -> tuple[str, str]:
    return (_remote_source(value), _remote_media_id(value))


def local_owned_games(database: Database) -> list[dict[str, Any]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT g.bgg_id, g.title, g.original_title, g.year_published,
                   g.item_type, c.coll_id, c.own, c.price_paid,
                   c.acquisition_date, c.acquired_from, c.quantity,
                   c.version_languages, c.version_publishers,
                   c.version_nickname
            FROM board_games g
            JOIN collection_entries c ON c.board_game_id = g.id
            WHERE c.own = 1
            ORDER BY g.title COLLATE NOCASE, g.bgg_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def load_floppy_links(database: Database) -> dict[int, dict[str, Any]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT bgg_id, source, media_id, item_db_id,
                   collection_entry_id, link_method
            FROM floppy_links
            """
        ).fetchall()
    return {int(row["bgg_id"]): dict(row) for row in rows}


def save_floppy_link(
    database: Database,
    *,
    bgg_id: int,
    source: str,
    media_id: str,
    item_db_id: int | None,
    collection_entry_id: int | None,
    link_method: str,
) -> None:
    now = datetime.now(UTC).isoformat()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO floppy_links (
                bgg_id, source, media_id, item_db_id,
                collection_entry_id, link_method, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bgg_id) DO UPDATE SET
                source = excluded.source,
                media_id = excluded.media_id,
                item_db_id = COALESCE(excluded.item_db_id, floppy_links.item_db_id),
                collection_entry_id = COALESCE(
                    excluded.collection_entry_id,
                    floppy_links.collection_entry_id
                ),
                link_method = excluded.link_method,
                updated_at = excluded.updated_at
            """,
            (
                bgg_id,
                source,
                media_id,
                item_db_id,
                collection_entry_id,
                link_method,
                now,
                now,
            ),
        )


def build_sync_preview(
    local_games: Iterable[dict[str, Any]],
    remote_games: Iterable[dict[str, Any]],
    collection_entries: Iterable[dict[str, Any]] = (),
    stored_links: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    local = list(local_games)
    remote = list(remote_games)
    collection = list(collection_entries)
    links = stored_links or {}

    by_bgg: dict[int, list[dict[str, Any]]] = {}
    by_title_year: dict[tuple[str, int | None], list[dict[str, Any]]] = {}
    by_coordinate: dict[tuple[str, str], list[dict[str, Any]]] = {}

    # Floppy omits held board games (blank status) from the media-list
    # endpoint even though they remain visible in the collection endpoint.
    # Build one de-duplicated matching surface from both sources, preferring
    # the richer media row when both expose the same source/media_id pair.
    candidates_by_coordinate: dict[tuple[str, str], dict[str, Any]] = {}
    uncoordinated_candidates: list[dict[str, Any]] = []

    for item in remote:
        coordinate = _remote_coordinate(item)
        if all(coordinate):
            candidates_by_coordinate[coordinate] = item
        else:
            uncoordinated_candidates.append(item)

    for entry in collection:
        coordinate = _remote_coordinate(entry)
        if all(coordinate):
            candidates_by_coordinate.setdefault(coordinate, entry)
        else:
            uncoordinated_candidates.append(entry)

    candidates = list(candidates_by_coordinate.values()) + uncoordinated_candidates

    for item in candidates:
        coordinate = _remote_coordinate(item)
        if all(coordinate):
            by_coordinate.setdefault(coordinate, []).append(item)

        bgg_id = _remote_bgg_id(item)
        if bgg_id is not None:
            by_bgg.setdefault(bgg_id, []).append(item)

        title = _normalize_title(_remote_title(item))
        year = _remote_year(item)
        if title and year is not None:
            by_title_year.setdefault((title, year), []).append(item)

    owned_coordinates = {
        _remote_coordinate(entry)
        for entry in collection
        if all(_remote_coordinate(entry))
    }

    matches: list[dict[str, Any]] = []
    already_owned: list[dict[str, Any]] = []
    needs_collection: list[dict[str, Any]] = []
    needs_media: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    for local_item in local:
        bgg_id = int(local_item["bgg_id"])
        base = _local_sync_identity(local_item)
        match: dict[str, Any] | None = None
        method: str | None = None

        saved = links.get(bgg_id)
        if saved:
            coordinate = (
                str(saved.get("source") or "").lower(),
                str(saved.get("media_id") or ""),
            )
            candidates = by_coordinate.get(coordinate, [])
            if len(candidates) == 1:
                match = candidates[0]
                method = "saved_link"
            elif len(candidates) > 1:
                ambiguous.append(
                    {
                        **base,
                        "reason": "duplicate_saved_link",
                        "candidates": [_remote_identity(item) for item in candidates],
                    }
                )
                continue

        if match is None:
            exact = by_bgg.get(bgg_id, [])
            if len(exact) == 1:
                match = exact[0]
                method = "bgg_id"
            elif len(exact) > 1:
                ambiguous.append(
                    {
                        **base,
                        "reason": "duplicate_bgg_id",
                        "candidates": [_remote_identity(item) for item in exact],
                    }
                )
                continue

        if match is None:
            local_year = local_item.get("year_published")
            key = (_normalize_title(local_item["title"]), local_year)
            fallback = (
                by_title_year.get(key, [])
                if local_year is not None
                else []
            )
            if len(fallback) == 1:
                match = fallback[0]
                method = "title_year"
            elif len(fallback) > 1:
                ambiguous.append(
                    {
                        **base,
                        "reason": "duplicate_title_year",
                        "candidates": [_remote_identity(item) for item in fallback],
                    }
                )
                continue

        if match is None:
            needs_media.append(base)
            continue

        remote_identity = _remote_identity(match)
        if method == "saved_link" and saved:
            # Collection rows do not expose the underlying Item database id;
            # retain the authoritative id persisted when BoardGameCompanion
            # created or linked the media.
            remote_identity["item_db_id"] = saved.get("item_db_id")
        matched = {
            **base,
            "match_method": method,
            "remote": remote_identity,
        }
        matches.append(matched)

        coordinate = (
            str(remote_identity.get("source") or "").lower(),
            str(remote_identity.get("media_id") or ""),
        )
        if coordinate in owned_coordinates:
            already_owned.append(matched)
        else:
            needs_collection.append(matched)

    exact_count = sum(item["match_method"] == "bgg_id" for item in matches)
    saved_count = sum(item["match_method"] == "saved_link" for item in matches)
    fallback_count = sum(item["match_method"] == "title_year" for item in matches)

    preview = {
        "local_owned": len(local),
        "remote_boardgames": len(remote),
        "remote_collection_entries": len(collection),
        "matched": len(matches),
        "matched_by_saved_link": saved_count,
        "matched_by_bgg_id": exact_count,
        "matched_by_title_year": fallback_count,
        "already_owned": len(already_owned),
        "needs_collection": len(needs_collection),
        "needs_media": len(needs_media),
        "missing_in_floppy": len(needs_media),
        "ambiguous": len(ambiguous),
        "actionable": len(needs_collection) + len(needs_media),
        "matches": matches,
        "already_owned_items": already_owned,
        "needs_collection_items": needs_collection,
        "needs_media_items": needs_media,
        # Compatibility with the P2A UI/API.
        "missing": needs_media,
        "ambiguous_items": ambiguous,
    }
    preview["plan_hash"] = make_sync_plan_hash(preview)
    return preview


def make_sync_plan_hash(preview: dict[str, Any]) -> str:
    stable = {
        "needs_collection": [
            {
                "bgg_id": item["bgg_id"],
                "source": item["remote"].get("source"),
                "media_id": item["remote"].get("media_id"),
                "item_db_id": item["remote"].get("item_db_id"),
            }
            for item in sorted(
                preview.get("needs_collection_items", []),
                key=lambda value: value["bgg_id"],
            )
        ],
        "needs_media": [
            {
                "bgg_id": item["bgg_id"],
                "title": item["title"],
                "year_published": item.get("year_published"),
            }
            for item in sorted(
                preview.get("needs_media_items", []),
                key=lambda value: value["bgg_id"],
            )
        ],
        "ambiguous": sorted(
            item["bgg_id"] for item in preview.get("ambiguous_items", [])
        ),
    }
    encoded = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_floppy_sync(
    database: Database,
    client: FloppyClient,
    *,
    expected_plan_hash: str,
    batch_size: int = 20,
) -> dict[str, Any]:
    batch_size = max(1, min(int(batch_size), 50))
    local = local_owned_games(database)
    local_by_bgg = {int(item["bgg_id"]): item for item in local}

    preview = build_sync_preview(
        local,
        client.boardgames(),
        client.collection_entries(),
        load_floppy_links(database),
    )
    if preview["plan_hash"] != expected_plan_hash:
        raise FloppyPlanChanged(
            "Floppy changed since the preview. Run the comparison again before syncing."
        )

    actions: list[tuple[str, dict[str, Any]]] = [
        ("collection", item)
        for item in preview["needs_collection_items"]
    ] + [
        ("media", item)
        for item in preview["needs_media_items"]
    ]
    actions = sorted(actions, key=lambda pair: pair[1]["bgg_id"])[:batch_size]

    results: list[dict[str, Any]] = []
    media_created = 0
    collection_created = 0
    skipped = 0
    failed = 0

    for action, item in actions:
        bgg_id = int(item["bgg_id"])
        local_item = local_by_bgg[bgg_id]
        try:
            if action == "collection":
                remote = item["remote"]
                item_db_id = _as_int(remote.get("item_db_id"))
                if item_db_id is None:
                    raise FloppyError(
                        "Matched Floppy item has no database item id",
                        kind="invalid_response",
                    )
                collection_entry = client.add_collection_entry(
                    item_db_id=item_db_id,
                    **_collection_fields(local_item),
                )
                collection_id = _as_int(collection_entry.get("id"))
                save_floppy_link(
                    database,
                    bgg_id=bgg_id,
                    source=str(remote.get("source") or ""),
                    media_id=str(remote.get("media_id") or ""),
                    item_db_id=item_db_id,
                    collection_entry_id=collection_id,
                    link_method=str(item.get("match_method") or "matched"),
                )
                collection_created += 1
                results.append(
                    {
                        "bgg_id": bgg_id,
                        "title": item["title"],
                        "status": "collection_added",
                        "source": remote.get("source"),
                        "media_id": remote.get("media_id"),
                        "collection_entry_id": collection_id,
                    }
                )
                continue

            tracked, source_mode, created_now = _create_missing_media(client, local_item)
            remote = _remote_identity(tracked)
            item_db_id = _as_int(remote.get("item_db_id"))
            if item_db_id is None:
                raise FloppyError(
                    "New Floppy media has no database item id",
                    kind="invalid_response",
                )

            if created_now:
                media_created += 1
            save_floppy_link(
                database,
                bgg_id=bgg_id,
                source=str(remote.get("source") or ""),
                media_id=str(remote.get("media_id") or ""),
                item_db_id=item_db_id,
                collection_entry_id=None,
                link_method=source_mode,
            )

            collection_entry = client.add_collection_entry(
                item_db_id=item_db_id,
                **_collection_fields(local_item),
            )
            collection_id = _as_int(collection_entry.get("id"))
            collection_created += 1
            save_floppy_link(
                database,
                bgg_id=bgg_id,
                source=str(remote.get("source") or ""),
                media_id=str(remote.get("media_id") or ""),
                item_db_id=item_db_id,
                collection_entry_id=collection_id,
                link_method=source_mode,
            )
            results.append(
                {
                    "bgg_id": bgg_id,
                    "title": item["title"],
                    "status": (
                        "media_and_collection_added"
                        if created_now
                        else "existing_media_collection_added"
                    ),
                    "source": remote.get("source"),
                    "media_id": remote.get("media_id"),
                    "collection_entry_id": collection_id,
                    "source_mode": source_mode,
                }
            )
        except FloppyError as exc:
            failed += 1
            results.append(
                {
                    "bgg_id": bgg_id,
                    "title": item["title"],
                    "status": "failed",
                    "error": str(exc),
                    "error_kind": exc.kind,
                    "http_status": exc.status_code,
                }
            )

    attempted = len(actions)
    remaining = max(0, int(preview["actionable"]) - attempted)
    result = {
        "plan_hash": expected_plan_hash,
        "attempted": attempted,
        "media_created": media_created,
        "collection_created": collection_created,
        "skipped": skipped,
        "failed": failed,
        "remaining_from_preview": remaining,
        "batch_size": batch_size,
        "results": results,
    }
    _record_sync_run(database, result)
    return result


def _create_missing_media(
    client: FloppyClient,
    local_item: dict[str, Any],
) -> tuple[dict[str, Any], str, bool]:
    bgg_id = int(local_item["bgg_id"])

    # Held board games with blank status are omitted from Floppy's media-list
    # endpoint, but the detail endpoint still exposes them. Check it before
    # creating anything so retries can safely reconcile prior partial writes.
    existing = client.boardgame_bgg_detail(bgg_id)
    if existing is not None:
        return existing, "bgg_existing", False

    try:
        return client.track_boardgame_bgg(bgg_id), "bgg", True
    except FloppyError as exc:
        if exc.kind == "timeout":
            # Floppy may finish the BGG provider request after our HTTP client
            # times out. Re-check the authoritative detail endpoint before
            # reporting failure or allowing a later retry to create a duplicate.
            for attempt in range(4):
                if attempt:
                    time.sleep(1)
                recovered = client.boardgame_bgg_detail(bgg_id)
                if recovered is not None:
                    return recovered, "bgg_recovered_after_timeout", False
            raise

        # Authentication and network errors are infrastructure errors:
        # do not hide them by creating a manual duplicate.
        if exc.kind in {"authentication", "unreachable"}:
            raise

    return (
        client.track_boardgame_manual(str(local_item["title"])),
        "manual_fallback",
        True,
    )


def _collection_fields(local_item: dict[str, Any]) -> dict[str, Any]:
    price = local_item.get("price_paid")
    try:
        purchase_price = float(price) if price not in (None, "") else None
    except (TypeError, ValueError):
        purchase_price = None
    return {
        "purchase_price": purchase_price,
        "purchase_location": local_item.get("acquired_from") or None,
        "collected_at": local_item.get("acquisition_date") or None,
    }


def _record_sync_run(database: Database, result: dict[str, Any]) -> None:
    now = datetime.now(UTC).isoformat()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO floppy_sync_runs (
                plan_hash, attempted, media_created, collection_created,
                skipped, failed, result_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["plan_hash"],
                result["attempted"],
                result["media_created"],
                result["collection_created"],
                result["skipped"],
                result["failed"],
                json.dumps(result, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )


def _local_sync_identity(local_item: dict[str, Any]) -> dict[str, Any]:
    return {
        "bgg_id": int(local_item["bgg_id"]),
        "title": local_item["title"],
        "year_published": local_item.get("year_published"),
        "item_type": local_item.get("item_type"),
    }


def _remote_identity(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _remote_title(item),
        "year": _remote_year(item),
        "source": _remote_source(item),
        "media_id": _remote_media_id(item),
        "bgg_id": _remote_bgg_id(item),
        "item_db_id": _remote_item_db_id(item),
        "item_id": item.get("item_id"),
    }
