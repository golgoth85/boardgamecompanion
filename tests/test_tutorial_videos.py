from __future__ import annotations

import json
from pathlib import Path

import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.tutorial_videos import (
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
