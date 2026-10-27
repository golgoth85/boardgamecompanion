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
    assert payload["items"][0]["players"]["recommended"] == "1, 2, 3"
    assert payload["items"][0]["players"]["best"] == "2"

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


class RotatingBggClient:
    def __init__(self) -> None:
        self.round = 1
        self.thing_calls = 0

    def hot(self, *, limit: int = 50):
        rows = (
            [
                {"bgg_id": 200, "title": "First Wave", "hot_rank": 1},
                {"bgg_id": 300, "title": "Second Wave", "hot_rank": 2},
            ]
            if self.round == 1
            else [
                {"bgg_id": 500, "title": "Third Wave", "hot_rank": 1},
                {"bgg_id": 600, "title": "Fourth Wave", "hot_rank": 2},
            ]
        )
        return rows[:limit]

    def things(self, bgg_ids):
        self.thing_calls += 1
        result = {}
        for bgg_id in bgg_ids:
            result[bgg_id] = {
                "bgg_id": bgg_id,
                "title": f"Candidate {bgg_id}",
                "year_published": 2026,
                "parent_bgg_id": None,
                "cover_url": None,
                "min_players": 1,
                "max_players": 4,
                "playing_time": 60,
                "min_play_time": 45,
                "max_play_time": 60,
                "bgg_average": 7.5 + (bgg_id % 3) / 10,
                "bgg_bayes_average": 7.2,
                "bgg_average_weight": 2.7,
                "bgg_rank": 100 + bgg_id,
                "bgg_best_players": "2",
                "bgg_recommended_players": "1, 2, 3, 4",
                "categories": ["Fantasy"],
                "mechanics": ["Deck Building"],
                "description": f"Description {bgg_id}",
            }
        return result


def test_suggestions_pool_retains_previous_hot_candidates(tmp_path: Path) -> None:
    database = _database(tmp_path)
    client = RotatingBggClient()
    service = SuggestionsService(
        database,
        client,
        cache_path=tmp_path / "suggestions.json",
        cache_ttl_seconds=0,
        candidate_limit=50,
        candidate_pool_limit=500,
    )

    first = service.list_suggestions(limit=10, refresh=True)
    assert first["source"] == "bgg_xml_api2_hot_history_catalog"
    assert first["candidate_count"] == 2
    assert first["history_retained_count"] == 0

    client.round = 2
    second = service.list_suggestions(limit=10, refresh=True)
    ids = {item["bgg_id"] for item in second["items"]}

    assert ids == {200, 300, 500, 600}
    assert second["candidate_count"] == 4
    assert second["current_hot_count"] == 2
    assert second["history_retained_count"] == 2
    assert second["candidate_pool_limit"] == 500


def test_suggestions_history_pool_is_bounded(tmp_path: Path) -> None:
    database = _database(tmp_path)
    cache_path = tmp_path / "suggestions.json"
    cached_items = []
    for bgg_id in range(1000, 1010):
        cached_items.append(
            {
                "bgg_id": bgg_id,
                "title": f"Old {bgg_id}",
                "year_published": 2025,
                "cover_url": None,
                "players": {"min": 1, "max": 4, "best": "2", "recommended": "1, 2"},
                "play_time": {"playing": 60, "min": 60, "max": 60},
                "bgg": {
                    "average": 7.5,
                    "bayes_average": 7.2,
                    "average_weight": 2.5,
                    "rank": 100,
                },
                "categories": ["Fantasy"],
                "mechanics": ["Deck Building"],
                "source_description": "Old candidate",
                "suggestion_score": 50.0,
                "score_parts": {"novelty": 0.2},
            }
        )
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generated_at": datetime.now(UTC).isoformat(),
                "items": cached_items,
            }
        ),
        encoding="utf-8",
    )
    client = RotatingBggClient()
    service = SuggestionsService(
        database,
        client,
        cache_path=cache_path,
        cache_ttl_seconds=0,
        candidate_limit=20,
        candidate_pool_limit=5,
    )

    payload = service.list_suggestions(limit=25, refresh=True)

    # candidate_pool_limit is never allowed below candidate_limit, so the
    # bounded pool contains at most 20 entries here.
    assert payload["candidate_pool_limit"] == 20
    assert payload["candidate_count"] <= 20


def _reference_game(connection, bgg_id: int, name: str, details: dict, **columns) -> None:
    now = datetime.now(UTC).isoformat()
    connection.execute(
        """
        INSERT INTO bgg_reference_games
        (bgg_id,name,year_published,rank,bayes_average,average,users_rated,
         image_url,description,details_json,source,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,'api',?,?)
        """,
        (
            bgg_id,
            name,
            columns.get("year", 2015),
            columns.get("rank", 500),
            columns.get("bayes", 6.8),
            columns.get("average", 7.4),
            columns.get("users_rated", 2000),
            f"https://cf.geekdo-images.com/{bgg_id}.jpg",
            columns.get("description", f"Catalog description {bgg_id}"),
            json.dumps(details),
            now,
            now,
        ),
    )


def test_suggestions_categories_offset_and_catalog_pool(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.transaction(immediate=True) as connection:
        _reference_game(
            connection, 700, "Catalog Duel",
            {"min_players": 2, "max_players": 2, "playing_time": 30,
             "bgg_average_weight": 1.8, "categories": ["Fantasy"],
             "mechanics": ["Deck Building"], "bgg_best_players": "2"},
            users_rated=900, average=7.9,
        )
        _reference_game(
            connection, 800, "Catalog Brick",
            {"min_players": 1, "max_players": 4, "playing_time": 180,
             "bgg_average_weight": 4.1, "categories": ["Economic"],
             "mechanics": ["Worker Placement"]},
            users_rated=30000,
        )
        # Never fetched from the API: no categories or mechanics, never a candidate.
        _reference_game(connection, 900, "Bare Title", {})
        # Owned games are excluded even when they come from the catalog.
        _reference_game(connection, 100, "Owned Game", {"mechanics": ["Deck Building"]})
    service = SuggestionsService(
        database,
        FakeBggClient(),
        cache_path=tmp_path / "suggestions.json",
        cache_ttl_seconds=3600,
    )

    payload = service.list_suggestions(limit=10, refresh=True)
    ids = [item["bgg_id"] for item in payload["items"]]
    assert set(ids) == {200, 300, 700, 800}
    assert payload["catalog_candidate_count"] == 2
    catalog = next(item for item in payload["items"] if item["bgg_id"] == 700)
    assert catalog["origin"] == "catalog"
    assert catalog["overview"]["source_description_available"] is True
    assert catalog["cover_url"] == "https://cf.geekdo-images.com/700.jpg"

    assert [item["bgg_id"] for item in service.list_suggestions(sort="trending")["items"]] == [200, 300]
    assert [item["bgg_id"] for item in service.list_suggestions(sort="duo")["items"]] == [200, 700]
    assert [item["bgg_id"] for item in service.list_suggestions(sort="light")["items"]] == [700]
    assert {item["bgg_id"] for item in service.list_suggestions(sort="heavy")["items"]} == {300, 800}
    assert [item["bgg_id"] for item in service.list_suggestions(sort="gems")["items"]] == [700]
    assert payload["category_counts"]["trending"] == 2

    first = service.list_suggestions(limit=2)
    second = service.list_suggestions(limit=2, offset=2)
    assert first["total_available"] == 4
    assert [item["bgg_id"] for item in first["items"] + second["items"]] == ids


def test_suggestions_set_aside_proposes_alternatives_and_restores(tmp_path: Path) -> None:
    database = _database(tmp_path)
    service = SuggestionsService(
        database,
        FakeBggClient(),
        cache_path=tmp_path / "suggestions.json",
        cache_ttl_seconds=3600,
    )
    first = service.list_suggestions(limit=1, refresh=True)
    assert first["items"][0]["bgg_id"] == 200
    assert first["proposed_count"] == 0

    assert service.mark_proposed([200])["proposed_count"] == 1
    alternative = service.list_suggestions(limit=1)
    assert alternative["items"][0]["bgg_id"] == 300
    assert alternative["proposed_count"] == 1
    assert alternative["category_counts"]["for_you"] == 1

    # Nothing is lost: the set-aside title is listed and can come back.
    proposed = service.list_suggestions(view="proposed")
    assert [item["bgg_id"] for item in proposed["items"]] == [200]
    assert proposed["items"][0]["proposed"]["round"] == 1

    service.mark_proposed([300])
    assert service.list_suggestions()["items"] == []
    assert [item["bgg_id"] for item in service.list_suggestions(view="proposed")["items"]] == [300, 200]

    assert service.restore_proposed([300]) == {"restored": 1, "proposed_count": 1}
    assert [item["bgg_id"] for item in service.list_suggestions()["items"]] == [300]
    assert service.restore_proposed()["proposed_count"] == 0
    assert [item["bgg_id"] for item in service.list_suggestions()["items"]] == [200, 300]


def test_suggestions_editorial_is_requested_in_small_batches(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.transaction(immediate=True) as connection:
        for offset in range(25):
            _reference_game(
                connection, 2000 + offset, f"Catalog {offset}",
                {"categories": ["Fantasy"], "mechanics": ["Deck Building"]},
            )

    class CountingEditorial(FakeEditorialService):
        def __init__(self) -> None:
            super().__init__()
            self.batches: list[int] = []

        def enrich(self, items):
            self.batches.append(len(items))
            return super().enrich(items)

    editorial = CountingEditorial()
    service = SuggestionsService(
        database,
        FakeBggClient(),
        cache_path=tmp_path / "suggestions.json",
        editorial_service=editorial,
        cache_ttl_seconds=3600,
    )
    payload = service.list_suggestions(limit=25, refresh=True)
    assert len(payload["items"]) == 25
    assert editorial.batches == [10, 10, 5]


def test_suggestions_old_cache_schema_is_rebuilt(tmp_path: Path) -> None:
    database = _database(tmp_path)
    cache_path = tmp_path / "suggestions.json"
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "generated_at": datetime.now(UTC).isoformat(),
                "items": [],
            }
        ),
        encoding="utf-8",
    )
    client = FakeBggClient()
    service = SuggestionsService(database, client, cache_path=cache_path, cache_ttl_seconds=3600)
    assert service.list_suggestions()["cache_state"] == "refreshed"
    assert client.hot_calls == 1
