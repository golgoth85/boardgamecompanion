from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from boardgamecompanion.crowdfunding_notifications import CrowdfundingNotificationProducer
from boardgamecompanion.database import Database


def _database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    now = datetime.now(UTC).isoformat()
    with db.transaction() as connection:
        game = connection.execute(
            """
            INSERT INTO board_games(
                bgg_id,title,item_type,source_metadata_json,created_at,updated_at
            ) VALUES(100,'Mage Knight','standalone','{}',?,?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO collection_entries(
                board_game_id,own,source_metadata_json,created_at,updated_at
            ) VALUES(?,1,'{}',?,?)
            """,
            (int(game.lastrowid), now, now),
        )
    return db


def _campaign(identifier: str, title: str):
    return {
        "id": identifier,
        "platform": "gamefound",
        "title": title,
        "description": "A tabletop campaign.",
        "project_url": f"https://gamefound.com/{identifier}",
    }


def test_crowdfunding_notifications_baseline_dedupe_and_relation(tmp_path: Path) -> None:
    db = _database(tmp_path)
    producer = CrowdfundingNotificationProducer(db)

    baseline = producer.scan([_campaign("old", "Mage Knight Ultimate Reprint")])
    assert baseline == {"matched": 1, "created": 1, "notified": 0}

    next_scan = producer.scan(
        [
            _campaign("old", "Mage Knight Ultimate Reprint"),
            _campaign("new", "Mage Knight: New Adventures"),
            _campaign("other", "Completely Different Game"),
        ]
    )
    assert next_scan["matched"] == 2
    assert next_scan["created"] == 1
    assert next_scan["notified"] == 1

    notifications = producer.notifications.list()
    assert notifications["unread_count"] == 1
    item = notifications["items"][0]
    assert item["category"] == "crowdfunding"
    assert item["related_bgg_id"] == 100
    assert item["metadata"]["matched_title"] == "Mage Knight"

    repeated = producer.scan([_campaign("new", "Mage Knight: New Adventures")])
    assert repeated["notified"] == 0
    assert producer.notifications.list()["unread_count"] == 1
