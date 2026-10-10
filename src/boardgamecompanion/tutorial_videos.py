from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

from boardgamecompanion.database import Database


class TutorialVideoError(RuntimeError):
    pass


class TutorialVideoNotConfigured(TutorialVideoError):
    pass


class TutorialVideoGameNotFound(TutorialVideoError):
    pass


_STOP_WORDS = {
    "a", "an", "and", "board", "edition", "game", "of", "the",
    "il", "la", "le", "lo", "di", "del", "della", "gioco",
}
_POSITIVE = {
    "it": ("come si gioca", "tutorial", "regole", "spiegazione", "impara a giocare"),
    "en": ("how to play", "tutorial", "rules", "learn to play", "teach the game"),
}
_NEGATIVE = (
    "review", "recensione", "unboxing", "trailer", "teaser", "preview",
    "playthrough", "let's play", "lets play", "full gameplay", "partita completa",
    "soundtrack", "music",
)
_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _duration_seconds(value: object) -> int | None:
    match = _DURATION_RE.match(str(value or ""))
    if not match:
        return None
    parts = {name: int(number or 0) for name, number in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def _thumbnail(snippet: dict[str, Any]) -> str | None:
    thumbnails = snippet.get("thumbnails") or {}
    for name in ("maxres", "standard", "high", "medium", "default"):
        item = thumbnails.get(name) or {}
        url = str(item.get("url") or "").strip()
        if url:
            return url
    return None


def _game_tokens(title: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _normalize(title).split()
        if len(token) >= 3 and token not in _STOP_WORDS
    )


def _tutorial_relevance(title: str, description: str, game_title: str, language: str) -> int:
    normalized_title = _normalize(title)
    haystack = _normalize(f"{title} {description[:1200]}")
    tokens = _game_tokens(game_title)
    if tokens:
        matched = sum(1 for token in tokens if token in haystack)
        coverage = matched / len(tokens)
        if coverage < 0.5 and _normalize(game_title) not in haystack:
            return -1
    positive_markers = tuple(_normalize(marker) for marker in _POSITIVE[language])
    positives = sum(1 for marker in positive_markers if marker in haystack)
    if positives == 0:
        return -1
    title_has_positive = any(marker in normalized_title for marker in positive_markers)
    negatives = sum(1 for marker in _NEGATIVE if _normalize(marker) in normalized_title)
    if negatives and not title_has_positive:
        return -1
    return int(coverage * 100) + positives * 30 - negatives * 35


def _publisher_names(raw_publishers: object, publishers_json: object) -> tuple[str, ...]:
    result: list[str] = []
    if raw_publishers:
        for part in re.split(r"[,;/|]", str(raw_publishers)):
            value = _normalize(part)
            if len(value) >= 4:
                result.append(value)
    try:
        publishers = json.loads(str(publishers_json or "[]"))
    except (TypeError, ValueError, RecursionError):
        publishers = []
    if isinstance(publishers, list):
        for item in publishers:
            value = _normalize(item)
            if len(value) >= 4:
                result.append(value)
    return tuple(dict.fromkeys(result))


class YouTubeTutorialService:
    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

    def __init__(
        self,
        database: Database,
        *,
        api_key: str | None,
        timeout_seconds: float = 20.0,
        search_results: int = 12,
    ):
        self.database = database
        self.api_key = (api_key or "").strip() or None
        self.timeout_seconds = float(timeout_seconds)
        self.search_results = max(4, min(int(search_results), 25))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _json_get(self, url: str, params: dict[str, object]) -> dict[str, Any]:
        if not self.api_key:
            raise TutorialVideoNotConfigured("YouTube Data API key is not configured")
        query = dict(params)
        query["key"] = self.api_key
        request = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(query),
            headers={"User-Agent": "BoardGameCompanion/YouTubeTutorials"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(4 * 1024 * 1024)
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", "replace")
            raise TutorialVideoError(
                f"YouTube API HTTP {exc.code}: {detail[:500]}"
            ) from exc
        except OSError as exc:
            raise TutorialVideoError(f"YouTube API request failed: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TutorialVideoError("YouTube API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TutorialVideoError("YouTube API returned an unexpected payload")
        return payload

    def _game_context(self, bgg_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT g.id,g.title,g.original_title,c.version_publishers,
                       e.publishers_json
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
                WHERE g.bgg_id=?
                """,
                (bgg_id,),
            ).fetchone()
        if row is None:
            raise TutorialVideoGameNotFound(f"Board game {bgg_id} not found")
        return {
            "board_game_id": int(row["id"]),
            "title": str(row["title"]),
            "original_title": str(row["original_title"] or ""),
            "publishers": _publisher_names(
                row["version_publishers"], row["publishers_json"]
            ),
        }

    def list_for_game(self, bgg_id: int) -> dict[str, object]:
        context = self._game_context(bgg_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT youtube_video_id,language,title,channel_id,channel_title,
                       thumbnail_url,duration_seconds,view_count,published_at,
                       is_official,official_reason,source_query,discovered_at,
                       verified_at
                FROM game_tutorial_videos
                WHERE board_game_id=?
                ORDER BY CASE language WHEN 'it' THEN 0 ELSE 1 END,
                         is_official DESC,view_count DESC,title COLLATE NOCASE
                """,
                (context["board_game_id"],),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["is_official"] = bool(item["is_official"])
            item["watch_url"] = (
                "https://www.youtube.com/watch?v="
                + str(item["youtube_video_id"])
            )
            item["embed_url"] = (
                "https://www.youtube-nocookie.com/embed/"
                + str(item["youtube_video_id"])
            )
            items.append(item)
        return {
            "bgg_id": bgg_id,
            "configured": self.configured,
            "count": len(items),
            "items": items,
        }

    def _search_language(
        self,
        *,
        game_title: str,
        publishers: tuple[str, ...],
        language: str,
    ) -> list[dict[str, Any]]:
        query_suffix = (
            "come si gioca tutorial regole gioco da tavolo"
            if language == "it"
            else "how to play tutorial rules board game"
        )
        search = self._json_get(
            self.SEARCH_URL,
            {
                "part": "snippet",
                "type": "video",
                "q": f'"{game_title}" {query_suffix}',
                "order": "viewCount",
                "maxResults": self.search_results,
                "videoEmbeddable": "true",
                "safeSearch": "moderate",
                "relevanceLanguage": language,
            },
        )
        ids = [
            str((item.get("id") or {}).get("videoId") or "").strip()
            for item in search.get("items") or []
            if isinstance(item, dict)
        ]
        ids = [value for value in ids if value]
        if not ids:
            return []

        details = self._json_get(
            self.VIDEOS_URL,
            {
                "part": "snippet,statistics,contentDetails,status",
                "id": ",".join(ids),
                "maxResults": len(ids),
            },
        )
        candidates: list[dict[str, Any]] = []
        for item in details.get("items") or []:
            if not isinstance(item, dict):
                continue
            video_id = str(item.get("id") or "").strip()
            snippet = item.get("snippet") or {}
            status = item.get("status") or {}
            statistics = item.get("statistics") or {}
            content = item.get("contentDetails") or {}
            if not video_id or status.get("embeddable") is False:
                continue
            title = str(snippet.get("title") or "").strip()
            description = str(snippet.get("description") or "")
            duration = _duration_seconds(content.get("duration"))
            if duration is not None and not 180 <= duration <= 7200:
                continue
            relevance = _tutorial_relevance(title, description, game_title, language)
            if relevance < 0:
                continue
            declared_language = str(
                snippet.get("defaultAudioLanguage")
                or snippet.get("defaultLanguage")
                or ""
            ).casefold()
            if declared_language and not declared_language.startswith(language):
                continue
            channel_title = str(snippet.get("channelTitle") or "").strip()
            normalized_channel = _normalize(channel_title)
            matched_publisher = next(
                (
                    publisher
                    for publisher in publishers
                    if publisher in normalized_channel
                    or normalized_channel in publisher
                ),
                None,
            )
            official = bool(matched_publisher)
            try:
                view_count = int(statistics.get("viewCount") or 0)
            except (TypeError, ValueError):
                view_count = 0
            candidates.append(
                {
                    "youtube_video_id": video_id,
                    "language": language,
                    "title": title,
                    "channel_id": str(snippet.get("channelId") or "") or None,
                    "channel_title": channel_title,
                    "thumbnail_url": _thumbnail(snippet),
                    "duration_seconds": duration,
                    "view_count": view_count,
                    "published_at": str(snippet.get("publishedAt") or "") or None,
                    "is_official": official,
                    "official_reason": (
                        f"publisher channel match: {matched_publisher}"
                        if matched_publisher
                        else None
                    ),
                    "source_query": f'"{game_title}" {query_suffix}',
                    "relevance_score": relevance,
                }
            )
        return candidates

    @staticmethod
    def _select(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        official = [item for item in candidates if item["is_official"]]
        community = [item for item in candidates if not item["is_official"]]
        if official:
            result.append(
                max(
                    official,
                    key=lambda item: (
                        int(item["relevance_score"]),
                        int(item["view_count"]),
                    ),
                )
            )
        if community:
            result.append(
                max(
                    community,
                    key=lambda item: (
                        int(item["view_count"]),
                        int(item["relevance_score"]),
                    ),
                )
            )
        return result

    def discover_due(
        self,
        *,
        limit: int = 3,
        refresh_seconds: int = 45 * 24 * 60 * 60,
        now: datetime | None = None,
    ) -> dict[str, object]:
        if not self.configured:
            raise TutorialVideoNotConfigured("YouTube Data API key is not configured")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        cutoff = (current - timedelta(seconds=max(3600, int(refresh_seconds)))).isoformat()
        cap = max(1, min(int(limit), 20))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id,g.title,
                       COUNT(v.youtube_video_id) AS video_count,
                       MAX(v.verified_at) AS last_verified_at,
                       s.last_attempt_at
                FROM board_games g
                JOIN collection_entries c ON c.board_game_id=g.id
                LEFT JOIN game_tutorial_videos v ON v.board_game_id=g.id
                LEFT JOIN tutorial_discovery_state s ON s.board_game_id=g.id
                WHERE COALESCE(c.own,0)=1
                  AND COALESCE(g.item_type,'standalone') != 'expansion'
                GROUP BY g.id
                HAVING s.last_attempt_at IS NULL
                    OR s.last_attempt_at<=?
                ORDER BY (COUNT(v.youtube_video_id)=0) DESC,
                         (s.last_attempt_at IS NULL) DESC,
                         COALESCE(s.last_attempt_at,'') ASC,
                         g.title COLLATE NOCASE
                LIMIT ?
                """,
                (cutoff, cap),
            ).fetchall()

        items: list[dict[str, object]] = []
        stopped_for_quota = False
        for row in rows:
            bgg_id = int(row["bgg_id"])
            try:
                result = self.discover(bgg_id)
                result_count = int(result.get("count") or 0)
                finished_at = datetime.now(UTC).isoformat()
                with self.database.transaction(immediate=True) as connection:
                    game_row = connection.execute(
                        "SELECT id FROM board_games WHERE bgg_id=?",
                        (bgg_id,),
                    ).fetchone()
                    if game_row is not None:
                        connection.execute(
                            """
                            INSERT INTO tutorial_discovery_state(
                                board_game_id,last_attempt_at,last_success_at,
                                last_result_count,last_error
                            ) VALUES(?,?,?,?,NULL)
                            ON CONFLICT(board_game_id) DO UPDATE SET
                                last_attempt_at=excluded.last_attempt_at,
                                last_success_at=excluded.last_success_at,
                                last_result_count=excluded.last_result_count,
                                last_error=NULL
                            """,
                            (
                                int(game_row["id"]),
                                finished_at,
                                finished_at,
                                result_count,
                            ),
                        )
                items.append(
                    {
                        "bgg_id": bgg_id,
                        "title": str(row["title"]),
                        "status": "succeeded",
                        "count": result_count,
                    }
                )
            except TutorialVideoError as exc:
                message = str(exc)
                finished_at = datetime.now(UTC).isoformat()
                with self.database.transaction(immediate=True) as connection:
                    game_row = connection.execute(
                        "SELECT id FROM board_games WHERE bgg_id=?",
                        (bgg_id,),
                    ).fetchone()
                    if game_row is not None:
                        connection.execute(
                            """
                            INSERT INTO tutorial_discovery_state(
                                board_game_id,last_attempt_at,last_success_at,
                                last_result_count,last_error
                            ) VALUES(?,?,NULL,NULL,?)
                            ON CONFLICT(board_game_id) DO UPDATE SET
                                last_attempt_at=excluded.last_attempt_at,
                                last_error=excluded.last_error
                            """,
                            (
                                int(game_row["id"]),
                                finished_at,
                                message[:1000],
                            ),
                        )
                items.append(
                    {
                        "bgg_id": bgg_id,
                        "title": str(row["title"]),
                        "status": "failed",
                        "error": message[:500],
                    }
                )
                lowered = message.casefold()
                if "http 403" in lowered or "quota" in lowered:
                    stopped_for_quota = True
                    break
        return {
            "attempted": len(items),
            "succeeded": sum(1 for item in items if item["status"] == "succeeded"),
            "failed": sum(1 for item in items if item["status"] == "failed"),
            "stopped_for_quota": stopped_for_quota,
            "items": items,
        }


    def discover(self, bgg_id: int) -> dict[str, object]:
        if not self.configured:
            raise TutorialVideoNotConfigured("YouTube Data API key is not configured")
        context = self._game_context(bgg_id)
        selected: list[dict[str, Any]] = []
        for language in ("it", "en"):
            candidates = self._search_language(
                game_title=context["title"],
                publishers=context["publishers"],
                language=language,
            )
            selected.extend(self._select(candidates))

        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "DELETE FROM game_tutorial_videos WHERE board_game_id=?",
                (context["board_game_id"],),
            )
            for item in selected:
                connection.execute(
                    """
                    INSERT INTO game_tutorial_videos(
                        board_game_id,youtube_video_id,language,title,
                        channel_id,channel_title,thumbnail_url,duration_seconds,
                        view_count,published_at,is_official,official_reason,
                        source_query,discovered_at,verified_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        context["board_game_id"],
                        item["youtube_video_id"],
                        item["language"],
                        item["title"],
                        item["channel_id"],
                        item["channel_title"],
                        item["thumbnail_url"],
                        item["duration_seconds"],
                        item["view_count"],
                        item["published_at"],
                        1 if item["is_official"] else 0,
                        item["official_reason"],
                        item["source_query"],
                        now,
                        now,
                    ),
                )
        return self.list_for_game(bgg_id)
