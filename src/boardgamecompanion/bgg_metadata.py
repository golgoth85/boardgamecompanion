from __future__ import annotations

import html
import json
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx

from boardgamecompanion.database import Database

BGG_API_ORIGIN = "https://boardgamegeek.com"
MAX_XML_BYTES = 2 * 1024 * 1024
MAX_METADATA_BYTES = 256 * 1024
MAX_THING_IDS = 20
BGG_IMAGE_HOSTS = frozenset(
    {"cf.geekdo-images.com", "cf.geekdo-static.com", "boardgamegeek.com"}
)


class BggMetadataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BggApiConfig:
    application_token: str
    timeout_seconds: float = 20.0
    min_interval_seconds: float = 5.0
    max_attempts: int = 2

    def __post_init__(self) -> None:
        if not self.application_token.strip():
            raise ValueError("BGG application token is required")
        if self.timeout_seconds <= 0 or self.min_interval_seconds < 0:
            raise ValueError("Invalid BGG API timing configuration")
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("BGG API max attempts must be between 1 and 3")


class BggApiClient:
    """Small server-side XML API2 client for exact canonical IDs only."""

    def __init__(
        self,
        config: BggApiConfig,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        rate_limiter: Callable[[str, float], None] | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self._persistent_rate_limiter = rate_limiter

    def _wait(self) -> None:
        if self._persistent_rate_limiter is not None:
            self._persistent_rate_limiter(
                "bgg:xmlapi2",
                self.config.min_interval_seconds,
            )
            return
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self.config.min_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._monotonic()

    def _request_things(self, identifiers: tuple[int, ...]) -> bytes:
        url = f"{BGG_API_ORIGIN}/xmlapi2/thing?id={','.join(str(value) for value in identifiers)}"
        response: httpx.Response | None = None
        content = b""
        for attempt in range(self.config.max_attempts):
            self._wait()
            try:
                client_context = (
                    nullcontext(self.client)
                    if self.client is not None
                    else httpx.Client(trust_env=False)
                )
                with client_context as client:
                    assert client is not None
                    with client.stream(
                        "GET",
                        url,
                        headers={
                            "Authorization": f"Bearer {self.config.application_token}",
                            "Accept": "application/xml, text/xml",
                            "Accept-Encoding": "identity",
                            "User-Agent": "BoardGameCompanion/0.1 BGG-metadata",
                        },
                        timeout=self.config.timeout_seconds,
                        follow_redirects=False,
                    ) as streamed:
                        response = streamed
                        content_encoding = streamed.headers.get(
                            "content-encoding", ""
                        ).strip().casefold()
                        if content_encoding not in {"", "identity"}:
                            raise BggMetadataError(
                                "BGG API content encoding is not allowed"
                            )
                        declared = streamed.headers.get("content-length", "").strip()
                        if declared.isdigit() and int(declared) > MAX_XML_BYTES:
                            raise BggMetadataError("BGG API response exceeds the byte limit")
                        chunks: list[bytes] = []
                        size = 0
                        for chunk in streamed.iter_bytes():
                            size += len(chunk)
                            if size > MAX_XML_BYTES:
                                raise BggMetadataError("BGG API response exceeds the byte limit")
                            chunks.append(chunk)
                        content = b"".join(chunks)
            except httpx.RequestError as exc:
                if attempt + 1 < self.config.max_attempts:
                    self._sleep(min(2**attempt, 5))
                    continue
                raise BggMetadataError("BGG API request failed") from exc
            if (
                response.status_code in {202, 429, 500, 502, 503, 504}
                and attempt + 1 < self.config.max_attempts
            ):
                retry_after = response.headers.get("retry-after", "").strip()
                delay = (
                    min(float(retry_after), 5.0)
                    if retry_after.isdigit()
                    else min(2**attempt, 5)
                )
                self._sleep(delay)
                continue
            break

        assert response is not None
        if 300 <= response.status_code < 400:
            raise BggMetadataError("BGG API redirect refused")
        if response.status_code in {401, 403}:
            raise BggMetadataError("BGG application token was rejected")
        if response.status_code != 200:
            raise BggMetadataError(f"BGG API returned HTTP {response.status_code}")
        return content

    def thing(self, bgg_id: int) -> dict[str, Any]:
        identifier = int(bgg_id)
        if identifier <= 0:
            raise ValueError("BGG ID must be positive")
        items = self.things([identifier])
        if identifier not in items:
            raise BggMetadataError("BGG API did not return exactly one item")
        return items[identifier]

    def things(self, bgg_ids: list[int] | tuple[int, ...]) -> dict[int, dict[str, Any]]:
        identifiers = tuple(dict.fromkeys(int(value) for value in bgg_ids))
        if not identifiers or len(identifiers) > MAX_THING_IDS:
            raise ValueError(f"BGG thing batch must contain between 1 and {MAX_THING_IDS} IDs")
        if any(value <= 0 for value in identifiers):
            raise ValueError("BGG IDs must be positive")
        content = self._request_things(identifiers)
        return _parse_things(content, expected_bgg_ids=set(identifiers))


def _attribute(node: ET.Element | None, name: str = "value") -> str | None:
    if node is None:
        return None
    value = node.attrib.get(name)
    return value.strip() if value and value.strip() else None


def _number_attribute(node: ET.Element | None, name: str = "value") -> float | None:
    value = _attribute(node, name)
    if value is None or value.upper() == "N/A":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _suggested_players(item: ET.Element) -> tuple[str | None, str | None]:
    poll = next(
        (
            node
            for node in item.findall("poll")
            if node.attrib.get("name") == "suggested_numplayers"
        ),
        None,
    )
    if poll is None:
        return None, None
    best: list[str] = []
    recommended: list[str] = []
    for result_group in poll.findall("results"):
        label = (result_group.attrib.get("numplayers") or "").strip()
        if not label:
            continue
        votes = {
            (node.attrib.get("value") or "").strip().casefold(): int(
                node.attrib.get("numvotes") or "0"
            )
            for node in result_group.findall("result")
            if (node.attrib.get("numvotes") or "0").isdigit()
        }
        best_votes = votes.get("best", 0)
        recommended_votes = votes.get("recommended", 0)
        not_recommended_votes = votes.get("not recommended", 0)
        if best_votes > 0 and best_votes >= recommended_votes and best_votes >= not_recommended_votes:
            best.append(label)
        if best_votes + recommended_votes > not_recommended_votes:
            recommended.append(label)
    return (
        ", ".join(best) or None,
        ", ".join(recommended) or None,
    )


def _suggested_age(item: ET.Element) -> str | None:
    poll = next(
        (
            node
            for node in item.findall("poll")
            if node.attrib.get("name") == "suggested_playerage"
        ),
        None,
    )
    candidates: list[tuple[int, str]] = []
    if poll is not None:
        for group in poll.findall("results"):
            for node in group.findall("result"):
                value = (node.attrib.get("value") or "").strip()
                votes = node.attrib.get("numvotes") or "0"
                if value and votes.isdigit():
                    candidates.append((int(votes), value))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return _attribute(item.find("minage"))

def _parse_item(item: ET.Element) -> dict[str, Any]:
    try:
        observed_id = int(item.attrib["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BggMetadataError("BGG API item has no valid ID") from exc

    names = item.findall("name")
    primary = next((node for node in names if node.attrib.get("type") == "primary"), None)
    title = _attribute(primary)
    if not title:
        raise BggMetadataError("BGG API item has no primary title")
    alternate_titles = tuple(
        dict.fromkeys(
            value
            for node in names
            if node is not primary
            for value in (_attribute(node),)
            if value and value != title
        )
    )
    alternate = alternate_titles[0] if alternate_titles else None

    links = item.findall("link")
    grouped: dict[str, list[str]] = {}
    for node in links:
        kind = node.attrib.get("type", "")
        value = _attribute(node)
        if kind and value and len(value) <= 500:
            grouped.setdefault(kind, []).append(value)

    raw_description = item.findtext("description") or ""
    description = html.unescape(raw_description).strip()[:20_000] or None
    image = (item.findtext("image") or "").strip() or None
    if image:
        image_parts = urlsplit(image)
        if (
            image_parts.scheme != "https"
            or (image_parts.hostname or "").lower() not in BGG_IMAGE_HOSTS
            or image_parts.username is not None
            or image_parts.password is not None
        ):
            image = None

    year_text = _attribute(item.find("yearpublished"))
    return {
        "bgg_id": observed_id,
        "title": title,
        "original_title": alternate,
        "alternate_titles": list(alternate_titles),
        "year_published": int(year_text) if year_text and year_text.isdigit() else None,
        "item_type": item.attrib.get("type"),
        "cover_url": image,
        "description": description,
        "publishers": grouped.get("boardgamepublisher", []),
        "categories": grouped.get("boardgamecategory", []),
        "designers": grouped.get("boardgamedesigner", []),
    }


def _parse_things(
    content: bytes,
    *,
    expected_bgg_ids: set[int],
) -> dict[int, dict[str, Any]]:
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError) as exc:
        raise BggMetadataError("BGG API returned invalid XML") from exc

    result: dict[int, dict[str, Any]] = {}
    for item in root.findall("item"):
        metadata = _parse_item(item)
        identifier = int(metadata["bgg_id"])
        if identifier not in expected_bgg_ids:
            raise BggMetadataError("BGG API returned a conflicting canonical ID")
        if identifier in result:
            raise BggMetadataError("BGG API returned a duplicate canonical ID")
        result[identifier] = metadata
    return result


def _parse_thing(content: bytes, *, expected_bgg_id: int) -> dict[str, Any]:
    items = _parse_things(content, expected_bgg_ids={expected_bgg_id})
    if set(items) != {expected_bgg_id}:
        raise BggMetadataError("BGG API did not return exactly one item")
    return items[expected_bgg_id]


class BggMetadataStore:
    def __init__(
        self,
        database: Database,
        client: BggApiClient | None,
        *,
        refresh_seconds: int = 30 * 24 * 60 * 60,
        retry_seconds: int = 24 * 60 * 60,
    ) -> None:
        self.database = database
        self.client = client
        self.refresh_seconds = int(refresh_seconds)
        self.retry_seconds = int(retry_seconds)

    def get(self, bgg_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT e.* FROM board_game_enrichments e
                   JOIN board_games g ON g.id=e.board_game_id
                   WHERE g.bgg_id=?""",
                (int(bgg_id),),
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        for key in ("publishers_json", "categories_json", "designers_json", "metadata_json"):
            value[key.removesuffix("_json")] = json.loads(value.pop(key))
        return value

    def _record_failure(self, bgg_id: int, exc: Exception, current: datetime) -> None:
        current_iso = current.isoformat()
        with self.database.transaction(immediate=True) as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id=?",
                (int(bgg_id),),
            ).fetchone()
            if game is None:
                raise BggMetadataError(f"Board game BGG #{bgg_id} not found") from exc
            connection.execute(
                """INSERT INTO board_game_enrichments
                   (board_game_id,source,external_id,next_refresh_at,consecutive_failures,last_error,created_at,updated_at)
                   VALUES (?,'bgg_xml_api2',?,?,1,?,?,?)
                   ON CONFLICT(board_game_id) DO UPDATE SET
                     next_refresh_at=excluded.next_refresh_at,
                     consecutive_failures=board_game_enrichments.consecutive_failures+1,
                     last_error=excluded.last_error,updated_at=excluded.updated_at""",
                (
                    game["id"],
                    str(bgg_id),
                    (current + timedelta(seconds=self.retry_seconds)).isoformat(),
                    str(exc)[:1000],
                    current_iso,
                    current_iso,
                ),
            )

    def _persist_metadata(
        self,
        bgg_id: int,
        metadata: dict[str, Any],
        current: datetime,
    ) -> None:
        current_iso = current.isoformat()
        raw = json.dumps(
            metadata,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(raw.encode()) > MAX_METADATA_BYTES:
            raise BggMetadataError("Normalized BGG metadata exceeds the byte limit")

        with self.database.transaction(immediate=True) as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id=?",
                (int(bgg_id),),
            ).fetchone()
            if game is None:
                raise BggMetadataError(f"Board game BGG #{bgg_id} not found")
            connection.execute(
                """INSERT INTO board_game_enrichments
                   (board_game_id,source,external_id,title,original_title,year_published,cover_url,description,
                    publishers_json,categories_json,designers_json,metadata_json,fetched_at,next_refresh_at,
                    consecutive_failures,last_error,created_at,updated_at)
                   VALUES (?,'bgg_xml_api2',?,?,?,?,?,?,?,?,?,?,?, ?,0,NULL,?,?)
                   ON CONFLICT(board_game_id) DO UPDATE SET
                    source=excluded.source,external_id=excluded.external_id,title=excluded.title,
                    original_title=excluded.original_title,year_published=excluded.year_published,
                    cover_url=excluded.cover_url,description=excluded.description,
                    publishers_json=excluded.publishers_json,categories_json=excluded.categories_json,
                    designers_json=excluded.designers_json,metadata_json=excluded.metadata_json,
                    fetched_at=excluded.fetched_at,next_refresh_at=excluded.next_refresh_at,
                    consecutive_failures=0,last_error=NULL,updated_at=excluded.updated_at""",
                (
                    game["id"],
                    str(bgg_id),
                    metadata["title"],
                    metadata["original_title"],
                    metadata["year_published"],
                    metadata["cover_url"],
                    metadata["description"],
                    json.dumps(metadata["publishers"]),
                    json.dumps(metadata["categories"]),
                    json.dumps(metadata["designers"]),
                    raw,
                    current_iso,
                    (current + timedelta(seconds=self.refresh_seconds)).isoformat(),
                    current_iso,
                    current_iso,
                ),
            )

    def refresh(
        self,
        bgg_id: int,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if self.client is None:
            raise BggMetadataError("BGG API is not configured")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        current_iso = current.isoformat()
        existing = self.get(bgg_id)
        if existing and not force and existing["next_refresh_at"] > current_iso:
            return existing
        try:
            metadata = self.client.thing(int(bgg_id))
            self._persist_metadata(int(bgg_id), metadata, current)
        except Exception as exc:
            self._record_failure(int(bgg_id), exc, current)
            raise

        result = self.get(bgg_id)
        assert result is not None
        return result

    def refresh_many(
        self,
        bgg_ids: list[int] | tuple[int, ...],
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> dict[int, dict[str, Any]]:
        if self.client is None:
            raise BggMetadataError("BGG API is not configured")
        identifiers = tuple(dict.fromkeys(int(value) for value in bgg_ids))
        if not identifiers or len(identifiers) > MAX_THING_IDS:
            raise ValueError(f"BGG metadata batch must contain between 1 and {MAX_THING_IDS} IDs")

        current = (now or datetime.now(UTC)).astimezone(UTC)
        current_iso = current.isoformat()
        pending: list[int] = []
        result: dict[int, dict[str, Any]] = {}
        for identifier in identifiers:
            existing = self.get(identifier)
            if existing and not force and existing["next_refresh_at"] > current_iso:
                result[identifier] = existing
            else:
                pending.append(identifier)

        if pending:
            try:
                metadata_by_id = self.client.things(pending)
            except Exception as exc:
                for identifier in pending:
                    self._record_failure(identifier, exc, current)
                raise

            for identifier in pending:
                metadata = metadata_by_id.get(identifier)
                if metadata is None:
                    exc = BggMetadataError(
                        f"BGG API returned no metadata for BGG #{identifier}"
                    )
                    self._record_failure(identifier, exc, current)
                    continue
                self._persist_metadata(identifier, metadata, current)
                stored = self.get(identifier)
                if stored is not None:
                    result[identifier] = stored

        return result
