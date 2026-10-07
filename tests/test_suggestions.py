from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from boardgamecompanion.database import Database
from boardgamecompanion.suggestions import SuggestionsService


class FakeEditorialService:
    def __init__(self) -> None:
        self.seen: list[dict] = []

    def enrich(self, items):
        self.seen = [dict(item) for item in items]
        enriched = []
        for item in items:
            copy = dict(item)
            copy["game_summary_it"] = "Sintesi narrativa in italiano."
            anchors = item.get("comparison_anchors") or []
            anchor = anchors[0]["title"] if anchors else "un gioco posseduto"
            copy["why_it_fits"] = f"Ricorda {anchor} per elementi condivisi, ma cambia ritmo."
            enriched.append(copy)
        return enriched


class FakeBggClient:
    def __init__(self) -> None:
        self.hot_calls = 0
        self.thing_calls = 0

    def hot(self, *, limit: int = 50):
        self.hot_calls += 1
        return [
            {"bgg_id": 100, "title": "Owned Game", "hot_rank": 1},
            {"bgg_id": 200, "title": "Strong Match", "hot_rank": 2},
            {"bgg_id": 300, "title": "Novel Game", "hot_rank": 3},
            {"bgg_id": 400, "title": "Expansion", "hot_rank": 4},
        ][:limit]

    def things(self, bgg_ids):
        self.thing_calls += 1
        data = {
            200: {
                "bgg_id": 200,
                "title": "Strong Match",
                "year_published": 2026,
                "parent_bgg_id": None,
                "cover_url": "https://cf.geekdo-images.com/match.jpg",
                "min_players": 1,
                "max_players": 4,
                "playing_time": 60,
                "min_play_time": 45,
                "max_play_time": 75,
                "bgg_average": 8.2,
                "bgg_bayes_average": 7.8,
                "bgg_average_weight": 2.8,
                "bgg_rank": 25,
                "bgg_best_players": "2",
                "bgg_recommended_players": "1, 2, 3",
                "categories": ["Fantasy"],
                "mechanics": ["Deck Building", "Cooperative Game"],
                "description": "A cooperative fantasy adventure.",
            },
            300: {
                "bgg_id": 300,
                "title": "Novel Game",
                "year_published": 2026,
                "parent_bgg_id": None,
                "cover_url": None,
                "min_players": 2,
                "max_players": 5,
                "playing_time": 90,
                "min_play_time": 60,
                "max_play_time": 90,
                "bgg_average": 7.7,
                "bgg_bayes_average": 7.3,
                "bgg_average_weight": 4.6,
                "bgg_rank": 90,
                "bgg_best_players": "4",
                "bgg_recommended_players": "3, 4",
                "categories": ["Economic"],
                "mechanics": ["Auction", "Commodity Speculation"],
            },
            400: {
                "bgg_id": 400,
                "title": "Expansion",
                "year_published": 2026,
                "parent_bgg_id": 999,
                "cover_url": None,
                "min_players": 2,
                "max_players": 4,
                "playing_time": 60,
                "min_play_time": 60,
                "max_play_time": 60,
                "bgg_average": 9.0,
                "bgg_bayes_average": 8.5,
                "bgg_average_weight": 2.7,
                "bgg_rank": None,
                "bgg_best_players": "2",
                "bgg_recommended_players": "2",
                "categories": ["Fantasy"],
                "mechanics": ["Deck Building"],
            },
        }
        return {identifier: data[identifier] for identifier in bgg_ids if identifier in data}


def _database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "bgc.sqlite3")
    db.initialize()
    now = datetime.now(UTC).isoformat()
    with db.transaction(immediate=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO board_games
            (bgg_id,title,item_type,playing_time,bgg_average,bgg_average_weight,
             source_metadata_json,created_at,updated_at)
            VALUES (100,'Owned Game','standalone',60,8.0,2.7,'{}',?,?)
            """,
            (now, now),
        )
        game_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO collection_entries
            (board_game_id,own,source_metadata_json,created_at,updated_at)
            VALUES (?,1,'{}',?,?)
            """,
            (game_id, now, now),
        )
        connection.execute(
            """
            INSERT INTO board_game_enrichments
            (board_game_id,source,external_id,title,categories_json,metadata_json,
             next_refresh_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                "bgg_xml_api2",
                "100",
                "Owned Game",
                json.dumps(["Fantasy"]),
                json.dumps(
                    {
                        "categories": ["Fantasy"],
                        "mechanics": ["Deck Building", "Cooperative Game"],
                    }
                ),
                now,
                now,
                now,
            ),
        )
    return db


def test_suggestions_exclude_owned_and_expansions_and_rank_by_profile(tmp_path: Path) -> None:
    database = _database(tmp_path)
    client = FakeBggClient()
    service = SuggestionsService(
        database,
        client,
        cache_path=tmp_path / "suggestions.json",
        cache_ttl_seconds=3600,
        candidate_limit=50,
    )

    payload = service.list_suggestions(limit=10, refresh=True)

    assert payload["cache_state"] == "refreshed"
    assert payload["owned_excluded_count"] == 1
    assert [item["bgg_id"] for item in payload["items"]] == [200, 300]
    assert payload["items"][0]["suggestion_score"] > payload["items"][1]["suggestion_score"]
    assert "Deck Building" in payload["items"][0]["reason"]
    assert "Tema/ambito: Fantasy." in payload["items"][0]["overview"]["summary"]
    assert "Meccaniche: Deck Building, Cooperative Game." in payload["items"][0]["overview"]["summary"]
    assert payload["items"][0]["overview"]["source_description_available"] is True

    novelty = service.list_suggestions(limit=10, sort="novelty")
    assert novelty["sort"] == "novelty"
    assert novelty["items"][0]["bgg_id"] == 300

    bgg = service.list_suggestions(limit=10, sort="bgg")
    assert bgg["sort"] == "bgg"
    assert bgg["items"][0]["bgg_id"] == 200

    assert client.hot_calls == 1
    assert client.thing_calls == 1


def test_suggestions_ground_editorial_copy_in_bgg_description_and_owned_anchors(tmp_path: Path) -> None:
    database = _database(tmp_path)
    editorial = FakeEditorialService()
    service = SuggestionsService(
        database,
        FakeBggClient(),
        cache_path=tmp_path / "suggestions.json",
        editorial_service=editorial,
        cache_ttl_seconds=3600,
        candidate_limit=50,
    )

    payload = service.list_suggestions(limit=1, refresh=True)

    assert payload["items"][0]["game_summary_it"] == "Sintesi narrativa in italiano."
    assert "Owned Game" in payload["items"][0]["why_it_fits"]
    assert "source_description" not in payload["items"][0]
    assert "comparison_anchors" not in payload["items"][0]

    assert editorial.seen[0]["source_description"] == "A cooperative fantasy adventure."
    assert editorial.seen[0]["comparison_anchors"][0]["title"] == "Owned Game"
    assert "Deck Building" in editorial.seen[0]["comparison_anchors"][0]["shared_mechanics"]


def test_suggestions_cache_survives_without_live_bgg_client(tmp_path: Path) -> None:
    database = _database(tmp_path)
    cache_path = tmp_path / "suggestions.json"
    live = SuggestionsService(
        database,
        FakeBggClient(),
        cache_path=cache_path,
        cache_ttl_seconds=3600,
    )
    first = live.list_suggestions(limit=1, refresh=True)

    restarted = SuggestionsService(
        database,
        None,
        cache_path=cache_path,
        cache_ttl_seconds=3600,
    )
    cached = restarted.list_suggestions(limit=1)

    assert cached["cache_state"] == "fresh"
    assert cached["items"] == first["items"]