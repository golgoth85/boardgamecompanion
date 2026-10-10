from __future__ import annotations

import json
from pathlib import Path

import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.tutorial_videos import (
    TutorialVideoError,
    TutorialVideoNotConfigured,
    YouTubeTutorialService,
)


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO board_games(
                bgg_id,title,original_title,source_metadata_json,created_at,updated_at
            ) VALUES(329082,'Radlands','Radlands','{}','now','now')
            """
        )
        game_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id=329082"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO collection_entries(
                board_game_id,own,source_metadata_json,created_at,updated_at
            ) VALUES(?,1,'{}','now','now')
            """,
            (game_id,),
        )
        connection.execute(
            """
            INSERT INTO board_game_enrichments(
                board_game_id,source,external_id,title,publishers_json,
                next_refresh_at,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                "test",
                "329082",
                "Radlands",
                json.dumps(["Roxley Games"]),
                "2099-01-01T00:00:00+00:00",
                "now",
                "now",
            ),
        )
    return database


def _video(video_id: str, title: str, channel: str, language: str, views: int):
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": f"{title} complete tutorial",
            "channelId": f"channel-{video_id}",
            "channelTitle": channel,
            "defaultAudioLanguage": language,
            "publishedAt": "2026-01-01T00:00:00Z",
            "thumbnails": {
                "high": {"url": f"https://img.youtube.test/{video_id}.jpg"}
            },
        },
        "statistics": {"viewCount": str(views)},
        "contentDetails": {"duration": "PT12M30S"},
        "status": {"embeddable": True},
    }


def test_discovery_keeps_official_and_top_viewed_community_per_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    service = YouTubeTutorialService(database, api_key="secret-key")

    search_ids = {
        "it": ["it-official", "it-low", "it-high", "it-review"],
        "en": ["en-official", "en-low", "en-high"],
    }
    videos = {
        "it-official": _video(
            "it-official", "Radlands: come si gioca - tutorial", "Roxley Games", "it", 250
        ),
        "it-low": _video(
            "it-low", "Radlands tutorial regole", "Giochi sul Tavolo", "it", 1000
        ),
        "it-high": _video(
            "it-high", "Radlands: come si gioca tutorial", "Meeple Italia", "it", 9000
        ),
        "it-review": _video(
            "it-review", "Radlands recensione", "Recensioni Boardgame", "it", 50000
        ),
        "en-official": _video(
            "en-official", "Radlands - How to Play", "Roxley Games", "en", 500
        ),
        "en-low": _video(
            "en-low", "Radlands how to play tutorial", "Tabletop A", "en", 2000
        ),
        "en-high": _video(
            "en-high", "Radlands how to play tutorial", "Tabletop B", "en", 12000
        ),
    }

    def fake_json_get(url: str, params: dict[str, object]):
        if url == service.SEARCH_URL:
            language = str(params["relevanceLanguage"])
            return {
                "items": [
                    {"id": {"videoId": video_id}}
                    for video_id in search_ids[language]
                ]
            }
        return {
            "items": [
                videos[video_id]
                for video_id in str(params["id"]).split(",")
            ]
        }

    monkeypatch.setattr(service, "_json_get", fake_json_get)

    result = service.discover(329082)

    assert result["count"] == 4
    chosen = {
        (item["language"], item["is_official"]): item
        for item in result["items"]
    }
    assert chosen[("it", True)]["youtube_video_id"] == "it-official"
    assert chosen[("it", False)]["youtube_video_id"] == "it-high"
    assert chosen[("en", True)]["youtube_video_id"] == "en-official"
    assert chosen[("en", False)]["youtube_video_id"] == "en-high"
    assert all(
        item["embed_url"].startswith("https://www.youtube-nocookie.com/embed/")
        for item in result["items"]
    )

    reloaded = YouTubeTutorialService(database, api_key=None).list_for_game(329082)
    assert reloaded["configured"] is False
    assert reloaded["count"] == 4


def test_discovery_requires_api_key(tmp_path: Path) -> None:
    database = _database(tmp_path)
    service = YouTubeTutorialService(database, api_key=None)

    with pytest.raises(TutorialVideoNotConfigured):
        service.discover(329082)



def test_discover_due_prioritizes_owned_games_without_videos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    service = YouTubeTutorialService(database, api_key="secret-key")
    seen: list[int] = []

    def fake_discover(bgg_id: int):
        seen.append(bgg_id)
        return {"bgg_id": bgg_id, "count": 2, "items": []}

    monkeypatch.setattr(service, "discover", fake_discover)

    result = service.discover_due(limit=3)

    assert seen == [329082]
    assert result["attempted"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["stopped_for_quota"] is False


def test_discover_due_prioritizes_missing_videos_before_unattempted_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    database = _database(tmp_path)
    with database.transaction(immediate=True) as connection:
        radlands_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id=329082"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO tutorial_discovery_state(
                board_game_id,last_attempt_at,last_success_at,
                last_result_count,last_error
            ) VALUES(?,? ,NULL,0,NULL)
            """,
            (radlands_id, "2026-01-01T00:00:00+00:00"),
        )
        cursor = connection.execute(
            """
            INSERT INTO board_games(
                bgg_id,title,original_title,source_metadata_json,created_at,updated_at
            ) VALUES(999001,'Aardvark','Aardvark','{}','now','now')
            """
        )
        other_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO collection_entries(
                board_game_id,own,source_metadata_json,created_at,updated_at
            ) VALUES(?,1,'{}','now','now')
            """,
            (other_id,),
        )
        connection.execute(
            """
            INSERT INTO game_tutorial_videos(
                board_game_id,youtube_video_id,language,title,channel_title,
                is_official,source_query,discovered_at,verified_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                other_id,
                "existing-video",
                "it",
                "Aardvark tutorial",
                "Test Channel",
                0,
                "query",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    service = YouTubeTutorialService(database, api_key="secret-key")
    seen: list[int] = []

    def fake_discover(bgg_id: int):
        seen.append(bgg_id)
        return {"bgg_id": bgg_id, "count": 0, "items": []}

    monkeypatch.setattr(service, "discover", fake_discover)
    result = service.discover_due(
        limit=1,
        refresh_seconds=45 * 24 * 60 * 60,
        now=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
    )

    assert result["attempted"] == 1
    assert seen == [329082]


def test_discover_due_skips_fresh_video_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    with database.transaction(immediate=True) as connection:
        game_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id=329082"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO game_tutorial_videos(
                board_game_id,youtube_video_id,language,title,channel_title,
                is_official,source_query,discovered_at,verified_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                "fresh-video",
                "it",
                "Radlands tutorial",
                "Test Channel",
                0,
                "query",
                "2026-10-10T10:00:00+00:00",
                "2026-10-10T10:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO tutorial_discovery_state(
                board_game_id,last_attempt_at,last_success_at,
                last_result_count,last_error
            ) VALUES(?,?,?,?,NULL)
            """,
            (
                game_id,
                "2026-10-10T10:00:00+00:00",
                "2026-10-10T10:00:00+00:00",
                1,
            ),
        )
    service = YouTubeTutorialService(database, api_key="secret-key")
    monkeypatch.setattr(
        service,
        "discover",
        lambda bgg_id: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    from datetime import UTC, datetime

    result = service.discover_due(
        limit=3,
        refresh_seconds=45 * 24 * 60 * 60,
        now=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
    )

    assert result["attempted"] == 0


def test_discover_due_stops_batch_on_youtube_quota_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    service = YouTubeTutorialService(database, api_key="secret-key")

    def quota_error(bgg_id: int):
        raise TutorialVideoError("YouTube API HTTP 403: quotaExceeded")

    monkeypatch.setattr(service, "discover", quota_error)

    result = service.discover_due(limit=3)

    assert result["attempted"] == 1
    assert result["failed"] == 1
    assert result["stopped_for_quota"] is True



def test_empty_tutorial_discovery_is_not_retried_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    service = YouTubeTutorialService(database, api_key="secret-key")
    calls: list[int] = []

    def empty_discover(bgg_id: int):
        calls.append(bgg_id)
        return {"bgg_id": bgg_id, "count": 0, "items": []}

    monkeypatch.setattr(service, "discover", empty_discover)
    from datetime import UTC, datetime

    first = service.discover_due(
        limit=3,
        refresh_seconds=45 * 24 * 60 * 60,
        now=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
    )
    second = service.discover_due(
        limit=3,
        refresh_seconds=45 * 24 * 60 * 60,
        now=datetime(2026, 10, 10, 12, 0, tzinfo=UTC),
    )

    assert first["attempted"] == 1
    assert first["items"][0]["count"] == 0
    assert second["attempted"] == 0
    assert calls == [329082]
