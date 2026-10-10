from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.bgg_metadata import BggMetadataError
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
                bgg_id,title,item_type,source_metadata_json,created_at,updated_at
            ) VALUES(201,'Owned Expansion','expansion','{}',?,?)
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
    assert minor_expansion_reason("Middara: Bounty Pack – The Pit Boss") == "content_pack"
    assert minor_expansion_reason("Living Card Game: Chapter Pack") == "content_pack"
    assert minor_expansion_reason("Arena: The Contest – Tanares Villain Pack") is None
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


def test_expansion_list_keeps_only_major_bgg_cohort(tmp_path: Path) -> None:
    db = _database(tmp_path)
    store = FakeMetadataStore(
        100,
        [
            {"bgg_id": 204, "title": "Tanares Adventures"},
            {"bgg_id": 205, "title": "Dragon Collection"},
            {"bgg_id": 206, "title": "Madness Box"},
            {"bgg_id": 207, "title": "Legendary Box"},
            {"bgg_id": 208, "title": "The Silver Dragon"},
            {"bgg_id": 209, "title": "Tanares Character Pack"},
        ],
        details={
            204: {
                "bgg_id": 204,
                "title": "Tanares Adventures",
                "item_type": "boardgameexpansion",
                "year_published": 2023,
                "bgg_average": 8.2,
                "bgg_num_owned": 2500,
            },
            205: {
                "bgg_id": 205,
                "title": "Dragon Collection",
                "item_type": "boardgameexpansion",
                "year_published": 2023,
                "bgg_average": 8.4,
                "bgg_num_owned": 830,
            },
            206: {
                "bgg_id": 206,
                "title": "Madness Box",
                "item_type": "boardgameexpansion",
                "year_published": 2023,
                "bgg_average": 8.0,
                "bgg_num_owned": 700,
            },
            207: {
                "bgg_id": 207,
                "title": "Legendary Box",
                "item_type": "boardgameexpansion",
                "year_published": 2023,
                "bgg_average": 8.1,
                "bgg_num_owned": 661,
            },
            208: {
                "bgg_id": 208,
                "title": "The Silver Dragon",
                "item_type": "boardgameexpansion",
                "year_published": 2024,
                "bgg_average": 8.0,
                "bgg_num_owned": 257,
            },
            209: {
                "bgg_id": 209,
                "title": "Tanares Character Pack",
                "item_type": "boardgameexpansion",
                "year_published": 2023,
                "bgg_average": 8.1,
                "bgg_num_owned": 553,
            },
        },
    )

    payload = ExpansionService(db, store).list_for_game(100)

    assert [item["bgg_id"] for item in payload["items"]] == [204, 205, 206, 207]
    assert payload["importance_reference_owned"] == 2500
    assert payload["importance_cutoff_owned"] == 625
    assert payload["excluded_minor_count"] == 0
    assert payload["excluded_unimportant_count"] == 2


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


def test_failed_refresh_never_establishes_empty_or_stale_baseline(
    tmp_path: Path,
) -> None:
    db = _database(tmp_path)

    class FailingMetadataStore(FakeMetadataStore):
        failing = True

        def refresh(self, bgg_id: int, *, force=False):
            if self.failing:
                raise BggMetadataError("temporary BGG outage")
            return super().refresh(bgg_id, force=force)

    store = FailingMetadataStore(
        100,
        [{"bgg_id": 202, "title": "The Lost Kingdom"}],
    )
    service = ExpansionService(db, store, refresh_seconds=24 * 60 * 60)
    with pytest.raises(BggMetadataError, match="temporary BGG outage"):
        service.scan_game(100)

    with db.connect() as connection:
        scan = connection.execute(
            "SELECT * FROM expansion_scan_state WHERE base_board_game_id=(SELECT id FROM board_games WHERE bgg_id=100)"
        ).fetchone()
        watches = connection.execute(
            "SELECT COUNT(*) FROM expansion_watch_state"
        ).fetchone()[0]
    assert scan["baseline_complete"] == 0
    assert scan["last_error"] == "temporary BGG outage"
    assert watches == 0
    next_due = datetime.fromisoformat(scan["next_check_at"])
    checked = datetime.fromisoformat(scan["last_checked_at"])
    assert (next_due - checked).total_seconds() == 3600

    # After recovery, these existing links become the baseline, not alerts.
    store.failing = False
    baseline = service.scan_game(100)
    assert baseline["new_relevant_count"] == 0
    assert service.notifications.list()["unread_count"] == 0


def test_missing_bgg_client_does_not_consume_initial_baseline(
    tmp_path: Path,
) -> None:
    db = _database(tmp_path)
    store = FakeMetadataStore(
        100,
        [{"bgg_id": 202, "title": "The Lost Kingdom"}],
    )
    original_client = store.client
    store.client = None
    service = ExpansionService(db, store)
    with pytest.raises(BggMetadataError, match="not configured"):
        service.scan_game(100)
    store.client = original_client
    assert service.scan_game(100)["new_relevant_count"] == 0
