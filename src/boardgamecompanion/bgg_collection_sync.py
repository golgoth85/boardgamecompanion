from __future__ import annotations

import json
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from boardgamecompanion.copies import ensure_physical_copies_for_collection_entry
from boardgamecompanion.database import Database

BGG_API_ORIGIN = "https://boardgamegeek.com"
MAX_COLLECTION_BYTES = 8 * 1024 * 1024
_SYNC_LOCK = threading.Lock()


class BggCollectionSyncError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BggCollectionConfig:
    application_token: str
    username: str
    timeout_seconds: float = 20.0
    min_interval_seconds: float = 5.0
    max_attempts: int = 5

    def __post_init__(self) -> None:
        if not self.application_token.strip():
            raise ValueError("BGG application token is required")
        if not self.username.strip():
            raise ValueError("BGG username is required")
        if self.timeout_seconds <= 0 or self.min_interval_seconds < 0:
            raise ValueError("Invalid BGG collection timing configuration")
        if not 1 <= self.max_attempts <= 8:
            raise ValueError("BGG collection max attempts must be between 1 and 8")


class BggCollectionClient:
    def __init__(
        self,
        config: BggCollectionConfig,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rate_limiter: Callable[[str, float], None] | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self._sleep = sleep
        self._rate_limiter = rate_limiter

    def _request(self, *, expansion: bool) -> bytes:
        params = {
            "username": self.config.username,
            "own": "1",
            "stats": "1",
        }
        if expansion:
            params["subtype"] = "boardgameexpansion"
        else:
            params["subtype"] = "boardgame"
            params["excludesubtype"] = "boardgameexpansion"
        url = f"{BGG_API_ORIGIN}/xmlapi2/collection?{urlencode(params)}"

        response: httpx.Response | None = None
        content = b""
        for attempt in range(self.config.max_attempts):
            if self._rate_limiter is not None:
                self._rate_limiter(
                    "bgg:xmlapi2",
                    self.config.min_interval_seconds,
                )
            try:
                context = (
                    _NullClientContext(self.client)
                    if self.client is not None
                    else httpx.Client(trust_env=False)
                )
                with context as client:
                    assert client is not None
                    with client.stream(
                        "GET",
                        url,
                        headers={
                            "Authorization": f"Bearer {self.config.application_token}",
                            "Accept": "application/xml, text/xml",
                            "Accept-Encoding": "identity",
                            "User-Agent": "BoardGameCompanion/0.1 BGG-collection-sync",
                        },
                        timeout=self.config.timeout_seconds,
                        follow_redirects=False,
                    ) as streamed:
                        response = streamed
                        if streamed.status_code == 202:
                            content = b""
                        else:
                            declared = streamed.headers.get("content-length", "").strip()
                            if declared.isdigit() and int(declared) > MAX_COLLECTION_BYTES:
                                raise BggCollectionSyncError(
                                    "BGG collection response exceeds the byte limit"
                                )
                            chunks: list[bytes] = []
                            size = 0
                            for chunk in streamed.iter_bytes():
                                size += len(chunk)
                                if size > MAX_COLLECTION_BYTES:
                                    raise BggCollectionSyncError(
                                        "BGG collection response exceeds the byte limit"
                                    )
                                chunks.append(chunk)
                            content = b"".join(chunks)
            except httpx.RequestError as exc:
                if attempt + 1 < self.config.max_attempts:
                    self._sleep(min(2 ** attempt, 5))
                    continue
                raise BggCollectionSyncError("BGG collection request failed") from exc

            assert response is not None
            if response.status_code == 202:
                if attempt + 1 >= self.config.max_attempts:
                    raise BggCollectionSyncError(
                        "BGG collection is still queued after the retry limit"
                    )
                self._sleep(min(max(self.config.min_interval_seconds, 1.0), 10.0))
                continue
            break

        assert response is not None
        if 300 <= response.status_code < 400:
            raise BggCollectionSyncError("BGG collection redirect refused")
        if response.status_code in {401, 403}:
            raise BggCollectionSyncError("BGG application token was rejected")
        if response.status_code != 200:
            raise BggCollectionSyncError(
                f"BGG collection returned HTTP {response.status_code}"
            )
        return content

    def owned_collection(self) -> list[dict[str, Any]]:
        base = _parse_collection(self._request(expansion=False), item_type="standalone")
        expansions = _parse_collection(
            self._request(expansion=True),
            item_type="expansion",
        )
        merged: dict[int, dict[str, Any]] = {}
        for item in [*base, *expansions]:
            merged[int(item["bgg_id"])] = item
        return sorted(merged.values(), key=lambda item: (str(item["title"]).casefold(), item["bgg_id"]))


class _NullClientContext:
    def __init__(self, client: httpx.Client | None) -> None:
        self.client = client

    def __enter__(self) -> httpx.Client | None:
        return self.client

    def __exit__(self, *_args: object) -> None:
        return None


def _int(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _float(value: str | None) -> float | None:
    if value is None or not str(value).strip() or str(value).strip().upper() == "N/A":
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _value(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    value = node.attrib.get("value")
    if value is None:
        value = node.text
    text = (value or "").strip()
    return text or None


def _parse_collection(content: bytes, *, item_type: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError) as exc:
        raise BggCollectionSyncError("BGG collection returned invalid XML") from exc

    rows: list[dict[str, Any]] = []
    for item in root.findall("item"):
        bgg_id = _int(item.attrib.get("objectid"))
        title = (item.findtext("name") or "").strip()
        if not bgg_id or not title:
            continue
        stats = item.find("stats")
        rating = stats.find("rating") if stats is not None else None
        ranks = rating.find("ranks") if rating is not None else None
        board_rank = None
        if ranks is not None:
            for rank in ranks.findall("rank"):
                if rank.attrib.get("name") == "boardgame":
                    board_rank = _int(rank.attrib.get("value"))
                    break
        status = item.find("status")
        status_attr = status.attrib if status is not None else {}
        rows.append(
            {
                "bgg_id": bgg_id,
                "coll_id": _int(item.attrib.get("collid")),
                "title": title,
                "year_published": _int(item.findtext("yearpublished")),
                "item_type": item_type,
                "min_players": _int(stats.attrib.get("minplayers")) if stats is not None else None,
                "max_players": _int(stats.attrib.get("maxplayers")) if stats is not None else None,
                "playing_time": _int(stats.attrib.get("playingtime")) if stats is not None else None,
                "min_play_time": _int(stats.attrib.get("minplaytime")) if stats is not None else None,
                "max_play_time": _int(stats.attrib.get("maxplaytime")) if stats is not None else None,
                "bgg_num_owned": _int(stats.attrib.get("numowned")) if stats is not None else None,
                "bgg_average": _float(_value(rating.find("average")) if rating is not None else None),
                "bgg_bayes_average": _float(_value(rating.find("bayesaverage")) if rating is not None else None),
                "bgg_average_weight": _float(_value(rating.find("averageweight")) if rating is not None else None),
                "bgg_rank": board_rank,
                "user_rating": _float(rating.attrib.get("value")) if rating is not None else None,
                "num_plays": _int(item.findtext("numplays")),
                "own": 1,
                "for_trade": _int(status_attr.get("fortrade")) or 0,
                "want": _int(status_attr.get("want")) or 0,
                "want_to_buy": _int(status_attr.get("wanttobuy")) or 0,
                "want_to_play": _int(status_attr.get("wanttoplay")) or 0,
                "previously_owned": _int(status_attr.get("prevowned")) or 0,
                "preordered": _int(status_attr.get("preordered")) or 0,
                "wishlist": _int(status_attr.get("wishlist")) or 0,
                "wishlist_priority": _int(status_attr.get("wishlistpriority")),
                "source_metadata": {
                    "sync_source": "bgg_xml_api2_collection",
                    "subtype": item.attrib.get("subtype"),
                    "status": status_attr,
                },
            }
        )
    return rows


@dataclass(frozen=True, slots=True)
class BggCollectionSyncResult:
    username: str
    row_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    bgg_ids: tuple[int, ...]
    created_bgg_ids: tuple[int, ...]
    synced_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "row_count": self.row_count,
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "unchanged_count": self.unchanged_count,
            "bgg_ids": list(self.bgg_ids),
            "created_bgg_ids": list(self.created_bgg_ids),
            "synced_at": self.synced_at,
        }


class BggCollectionSyncService:
    def __init__(
        self,
        database: Database,
        client: BggCollectionClient,
        *,
        interval_seconds: int = 6 * 60 * 60,
    ) -> None:
        self.database = database
        self.client = client
        self.interval_seconds = int(interval_seconds)

    def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM bgg_collection_sync_state WHERE id=1"
            ).fetchone()
        if row is None:
            return {
                "last_attempt_at": None,
                "last_success_at": None,
                "last_error": None,
                "last_result": None,
                "due": True,
                "interval_seconds": self.interval_seconds,
            }
        last_success = (
            datetime.fromisoformat(row["last_success_at"]).astimezone(UTC)
            if row["last_success_at"]
            else None
        )
        due = (
            last_success is None
            or current >= last_success + timedelta(seconds=self.interval_seconds)
        )
        try:
            last_result = json.loads(row["last_result_json"]) if row["last_result_json"] else None
        except json.JSONDecodeError:
            last_result = None
        return {
            "last_attempt_at": row["last_attempt_at"],
            "last_success_at": row["last_success_at"],
            "last_error": row["last_error"],
            "last_result": last_result,
            "due": due,
            "interval_seconds": self.interval_seconds,
        }

    def is_due(self, *, now: datetime | None = None) -> bool:
        return bool(self.status(now=now)["due"])

    def sync_if_due(self) -> BggCollectionSyncResult | None:
        if not self.is_due():
            return None
        return self.sync(force=False)

    def sync(self, *, force: bool = True) -> BggCollectionSyncResult | None:
        if not _SYNC_LOCK.acquire(blocking=False):
            return None
        try:
            if not force and not self.is_due():
                return None
            now = datetime.now(UTC).isoformat()
            self._record_attempt(now)
            try:
                items = self.client.owned_collection()
                result = self._persist(items, synced_at=now)
            except Exception as exc:
                self._record_error(now, exc)
                raise
            self._record_success(result)
            return result
        finally:
            _SYNC_LOCK.release()

    def _record_attempt(self, timestamp: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO bgg_collection_sync_state(id,last_attempt_at,updated_at)
                VALUES (1,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at,
                    updated_at=excluded.updated_at
                """,
                (timestamp, timestamp),
            )

    def _record_error(self, timestamp: str, exc: Exception) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE bgg_collection_sync_state
                SET last_error=?, updated_at=?
                WHERE id=1
                """,
                (str(exc)[:1000], timestamp),
            )

    def _record_success(self, result: BggCollectionSyncResult) -> None:
        payload = json.dumps(
            result.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE bgg_collection_sync_state
                SET last_success_at=?, last_error=NULL,
                    last_result_json=?, updated_at=?
                WHERE id=1
                """,
                (result.synced_at, payload, result.synced_at),
            )

    def _persist(
        self,
        items: list[dict[str, Any]],
        *,
        synced_at: str,
    ) -> BggCollectionSyncResult:
        created = updated = unchanged = 0
        created_ids: list[int] = []
        all_ids: list[int] = []
        with self.database.transaction() as connection:
            for item in items:
                bgg_id = int(item["bgg_id"])
                all_ids.append(bgg_id)
                existing_board = connection.execute(
                    "SELECT * FROM board_games WHERE bgg_id=?",
                    (bgg_id,),
                ).fetchone()
                board_id, board_changed, was_created = self._upsert_board(
                    connection,
                    item,
                    synced_at,
                    existing_board,
                )
                existing_entry = None
                coll_id = item.get("coll_id")
                if coll_id is not None:
                    existing_entry = connection.execute(
                        "SELECT * FROM collection_entries WHERE coll_id=?",
                        (coll_id,),
                    ).fetchone()
                if existing_entry is None:
                    existing_entry = connection.execute(
                        "SELECT * FROM collection_entries WHERE board_game_id=? ORDER BY id LIMIT 1",
                        (board_id,),
                    ).fetchone()
                entry_changed, entry_id = self._upsert_entry(
                    connection,
                    item,
                    board_id,
                    synced_at,
                    existing_entry,
                )
                ensure_physical_copies_for_collection_entry(
                    connection,
                    entry_id,
                    synced_at,
                )

                if was_created:
                    created += 1
                    created_ids.append(bgg_id)
                elif board_changed or entry_changed:
                    updated += 1
                else:
                    unchanged += 1

            connection.execute(
                """
                INSERT INTO import_runs(
                    source_type,source_filename,sha256,row_count,
                    created_count,updated_count,unchanged_count,imported_at
                ) VALUES ('bgg_xml_api2_collection',?,?, ?,?,?,?,?)
                """,
                (
                    f"BGG:{self.client.config.username}",
                    "",
                    len(items),
                    created,
                    updated,
                    unchanged,
                    synced_at,
                ),
            )

        return BggCollectionSyncResult(
            username=self.client.config.username,
            row_count=len(items),
            created_count=created,
            updated_count=updated,
            unchanged_count=unchanged,
            bgg_ids=tuple(all_ids),
            created_bgg_ids=tuple(created_ids),
            synced_at=synced_at,
        )

    @staticmethod
    def _upsert_board(connection, item, now, existing):
        columns = {
            "title": item["title"],
            "year_published": item.get("year_published"),
            "item_type": item.get("item_type"),
            "min_players": item.get("min_players"),
            "max_players": item.get("max_players"),
            "playing_time": item.get("playing_time"),
            "min_play_time": item.get("min_play_time"),
            "max_play_time": item.get("max_play_time"),
            "bgg_average": item.get("bgg_average"),
            "bgg_bayes_average": item.get("bgg_bayes_average"),
            "bgg_average_weight": item.get("bgg_average_weight"),
            "bgg_rank": item.get("bgg_rank"),
            "bgg_num_owned": item.get("bgg_num_owned"),
        }
        if existing is None:
            values = {"bgg_id": int(item["bgg_id"]), **columns}
            names = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            cursor = connection.execute(
                f"INSERT INTO board_games({names},created_at,updated_at) VALUES ({placeholders},?,?)",
                (*values.values(), now, now),
            )
            return int(cursor.lastrowid), True, True

        changed = False
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in columns.items():
            if value is None:
                continue
            if existing[key] != value:
                changed = True
                assignments.append(f"{key}=?")
                params.append(value)
        if changed:
            assignments.append("updated_at=?")
            params.extend([now, existing["id"]])
            connection.execute(
                f"UPDATE board_games SET {', '.join(assignments)} WHERE id=?",
                params,
            )
        return int(existing["id"]), changed, False

    @staticmethod
    def _upsert_entry(connection, item, board_game_id, now, existing):
        source_json = json.dumps(
            item.get("source_metadata") or {},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        incoming = {
            "coll_id": item.get("coll_id"),
            "board_game_id": board_game_id,
            "user_rating": item.get("user_rating"),
            "num_plays": item.get("num_plays"),
            "own": 1,
            "for_trade": item.get("for_trade", 0),
            "want": item.get("want", 0),
            "want_to_buy": item.get("want_to_buy", 0),
            "want_to_play": item.get("want_to_play", 0),
            "previously_owned": item.get("previously_owned", 0),
            "preordered": item.get("preordered", 0),
            "wishlist": item.get("wishlist", 0),
            "wishlist_priority": item.get("wishlist_priority"),
            "source_metadata_json": source_json,
        }
        if existing is None:
            names = ", ".join(incoming)
            placeholders = ", ".join("?" for _ in incoming)
            cursor = connection.execute(
                f"INSERT INTO collection_entries({names},created_at,updated_at) VALUES ({placeholders},?,?)",
                (*incoming.values(), now, now),
            )
            return True, int(cursor.lastrowid)

        changed = False
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in incoming.items():
            if key in {"user_rating", "num_plays", "wishlist_priority"} and value is None:
                continue
            if existing[key] != value:
                changed = True
                assignments.append(f"{key}=?")
                params.append(value)
        if changed:
            assignments.append("updated_at=?")
            params.extend([now, existing["id"]])
            connection.execute(
                f"UPDATE collection_entries SET {', '.join(assignments)} WHERE id=?",
                params,
            )
        return changed, int(existing["id"])
