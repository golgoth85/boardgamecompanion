from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from boardgamecompanion.database import Database
from boardgamecompanion.expansions import ExpansionService, minor_expansion_reason


class FakeClient:
    def __init__(self, details: dict[int, dict[str, Any]]):
        self.details = details

    def things(self, identifiers):
        return {
            int(identifier): self.details[int(identifier)]
            for identifier in identifiers
            if int(identifier) in self.details
        }


class FakeMetadataStore:
    def __init__(self, base_id: int, expansions: list[dict[str, Any]], details=None):
        self.base_id = base_id
        self.expansions = list(expansions)
        self.client = FakeClient(details or {})

    def _base(self):
        return {
            "metadata": {
                "bgg_id": self.base_id,
                "title": "Base Game",
                "item_type": "boardgame",
                "expansions": list(self.expansions),
            }
        }

    def get(self, bgg_id: int):
        if int(bgg_id) == self.base_id:
            return self._base()
        detail = self.client.details.get(int(bgg_id))
        return {"metadata": detail} if detail else None

    def refresh(self, bgg_id: int, *, force=False):
        assert int(bgg_id) == self.base_id
        return self._base()


def _database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    now = datetime.now(UTC).isoformat()
    with db.transaction() as connection:
        base = connection.execute(
            """
            INSERT INTO board_games(
                bgg_id,title,item_type,source_metadata_json,created_at,updated_at
            ) VALUES(100,'Base Game','standalone','{}',?,?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO collection_entries(
                board_game_id,own,source_metadata_json,created_at,updated_at
            ) VALUES(?,1,'{}',?,?)
            """,
            (int(base.lastrowid), now, now),
        )
        owned_expansion = connection.execute(
            """
            INSERT INTO board_games(
                bgg_id,title,item_type,parent_bgg_id,source_metadata_json,created_at,updated_at
            ) VALUES(201,'Owned Expansion','expansion',100,'{}',?,?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO collection_entries(
                board_game_id,own,source_metadata_json,created_at,updated_at
            ) VALUES(?,1,'{}',?,?)
            """,
            (int(owned_expansion.lastrowid), now, now),
        )
    return db


def test_major_expansion_filter_excludes_minor_addons() -> None:
    assert minor_expansion_reason("Game: Promo Pack") == "promo"
    assert minor_expansion_reason("Game: Miniatures Set") == "miniature"
    assert minor_expansion_reason("Game: Metal Coins") == "coins"
    assert minor_expansion_reason("Game: The Lost Kingdom") is None


def test_expansion_list_marks_owned_and_filters_micro_addons(tmp_path: Path) -> None:
    db = _database(tmp_path)
    store = FakeMetadataStore(
        100,
        [
            {"bgg_id": 201, "title": "Owned Expansion"},
            {"bgg_id": 202, "title": "The Lost Kingdom"},
            {"bgg_id": 203, "title": "Promo Pack"},
        ],
        details={
            201: {
                "bgg_id": 201,
                "title": "Owned Expansion",
                "item_type": "boardgameexpansion",
                "year_published": 2024,
                "cover_url": "https://cf.geekdo-images.com/owned.jpg",
            },
            202: {
                "bgg_id": 202,
                "title": "The Lost Kingdom",
                "item_type": "boardgameexpansion",
                "year_published": 2026,
                "cover_url": "https://cf.geekdo-images.com/lost.jpg",
            },
        },
    )
    payload = ExpansionService(db, store).list_for_game(100)
    assert [item["bgg_id"] for item in payload["items"]] == [202, 201]
    assert payload["items"][0]["owned"] is False
    assert payload["items"][1]["owned"] is True
    assert payload["missing_count"] == 1
    assert payload["owned_count"] == 1
    assert payload["excluded_minor_count"] == 1


def test_expansion_watch_baselines_then_notifies_only_new_relevant_links(
    tmp_path: Path,
) -> None:
    db = _database(tmp_path)
    store = FakeMetadataStore(
        100,
        [{"bgg_id": 201, "title": "Owned Expansion"}],
    )
    service = ExpansionService(db, store, refresh_seconds=3600)

    first = service.scan_game(100)
    assert first["new_relevant_count"] == 0
    assert service.notifications.list()["unread_count"] == 0

    store.expansions.extend(
        [
            {"bgg_id": 202, "title": "The Lost Kingdom"},
            {"bgg_id": 203, "title": "Promo Pack"},
        ]
    )
    second = service.scan_game(100)
    assert second["new_relevant_count"] == 1
    notices = service.notifications.list()
    assert notices["unread_count"] == 1
    assert notices["items"][0]["category"] == "expansion"
    assert notices["items"][0]["metadata"]["expansion_bgg_id"] == 202

    third = service.scan_game(100)
    assert third["new_relevant_count"] == 0
    assert service.notifications.list()["unread_count"] == 1
