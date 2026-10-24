from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from boardgamecompanion.bgg_reference import (
    BggReferenceCatalog,
    BggReferenceImporter,
    ReferenceSettings,
    get_sync_state,
    save_reference_settings,
)
from boardgamecompanion.bgg_reference_worker import BggReferenceWorker
from boardgamecompanion.database import Database

HEADER = (
    "id,name,yearpublished,rank,bayesaverage,average,usersrated,is_expansion,"
    "abstracts_rank,cgs_rank,childrensgames_rank,familygames_rank,partygames_rank,"
    "strategygames_rank,thematic_rank,wargames_rank\n"
)
YEAR = 2026
DUMP = (
    HEADER
    + "10,Popular,2010,5,7,7.5,5000,0,,,,,,,,\n"
    + "11,Upcoming Hit,0,0,0,0,10,0,,,,,,,,\n"
    + "12,Old Obscure,1999,0,0,0,5,0,,,,,,,,\n"
    + "13,Recent Quiet,2026,0,0,0,3,0,,,,,,,,\n"
).encode()


class FakeClient:
    """Serves IDs up to ``last_id``; ``overrides`` customise single items."""

    def __init__(self, last_id: int, overrides: dict[int, dict] | None = None) -> None:
        self.last_id = last_id
        self.overrides = overrides or {}
        self.requests: list[list[int]] = []

    def things_with_xml(self, ids):
        self.requests.append(list(ids))
        result = {}
        for bgg_id in ids:
            if bgg_id > self.last_id or bgg_id in self.overrides and self.overrides[bgg_id] is None:
                continue
            metadata = {
                "bgg_id": bgg_id,
                "title": f"Title {bgg_id}",
                "item_type": "boardgame",
                "year_published": 2026,
                "bgg_users_rated": 20,
                "bgg_wishing": 0,
                "alternate_titles": [],
                **self.overrides.get(bgg_id, {}),
            }
            result[bgg_id] = (metadata, f"<item id='{bgg_id}'/>")
        return result


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    return database


def worker(database: Database, client, now: datetime | None = None) -> BggReferenceWorker:
    clock = now or datetime(YEAR, 10, 24, 12, tzinfo=UTC)
    return BggReferenceWorker(database, lambda: client, now=lambda: clock)


def row(database: Database, bgg_id: int):
    with database.connect() as connection:
        return connection.execute("SELECT * FROM bgg_reference_games WHERE bgg_id=?", (bgg_id,)).fetchone()


def test_without_token_nothing_happens(database: Database) -> None:
    assert worker(database, None).run_once()["status"] == "no_token"
    assert row(database, 10)["api_checked_at"] is None


def test_zero_budget_suspends(database: Database) -> None:
    save_reference_settings(database, ReferenceSettings(daily_budget=0))
    client = FakeClient(20)
    assert worker(database, client).run_once()["status"] == "suspended"
    assert client.requests == []


def test_new_ids_stop_after_three_empty_batches_and_keep_cursor(database: Database) -> None:
    client = FakeClient(25, {11: None})
    summary = worker(database, client).run_once()
    assert summary["status"] == "ok"
    # ids 14..25 are new; then three empty batches end the scan
    new_rows = [row(database, i) for i in range(14, 26)]
    assert all(r is not None and r["source"] == "api" for r in new_rows)
    assert row(database, 26) is None  # beyond the last real ID
    assert get_sync_state(database, "new_id_cursor") == "25"
    scan = [r for r in client.requests if r[0] >= 14]
    assert scan[-3:] == [list(range(s, s + 20)) for s in (34, 54, 74)]
    # once per day: a second run does not rescan
    before = len(client.requests)
    worker(database, client).run_once()
    assert not any(r[0] > 25 for r in client.requests[before:])


def test_budget_is_respected_and_resets_next_day(database: Database) -> None:
    save_reference_settings(database, ReferenceSettings(daily_budget=2))
    client = FakeClient(10_000)
    summary = worker(database, client).run_once()
    assert summary["status"] == "budget_exhausted" and summary["requests"] == 2
    again = worker(database, client).run_once()
    assert again["requests"] == 0
    tomorrow = datetime(YEAR, 10, 25, 12, tzinfo=UTC)
    assert worker(database, client, tomorrow).run_once()["requests"] == 2


def test_candidates_admit_by_wishing_and_old_titles_are_left_alone(database: Database) -> None:
    client = FakeClient(
        13,
        {
            11: {"year_published": None, "bgg_wishing": 80, "bgg_users_rated": 10},
            13: {"year_published": 2026, "bgg_wishing": 5, "bgg_users_rated": 3},
        },
    )
    worker(database, client).run_once()
    upcoming = row(database, 11)
    assert upcoming["admission_reason"] == "upcoming" and upcoming["admission_until"] > "2026-10-24"
    assert row(database, 13)["admission_reason"] is None
    assert row(database, 12)["api_checked_at"] is None  # older than two years, below threshold
    names = [i["bgg_id"] for i in BggReferenceCatalog(database).search("upcoming")]
    assert names == [11]


def test_admitted_rotation_rechecks_after_14_days_and_promotes_by_votes(database: Database) -> None:
    client = FakeClient(13, {10: {"bgg_users_rated": 5100}})
    worker(database, client).run_once()
    first = row(database, 10)
    assert first["users_rated"] == 5100 and first["next_check_at"] > "2026-11-06"
    calls = len(client.requests)
    worker(database, client).run_once()
    assert not any(10 in r for r in client.requests[calls:])
    later = datetime(YEAR, 11, 8, 12, tzinfo=UTC)
    worker(database, client, later).run_once()
    assert any(10 in r for r in client.requests[calls:])


def test_missing_id_in_non_empty_batch_is_marked_removed_not_deleted(database: Database) -> None:
    client = FakeClient(13, {13: None})
    worker(database, client).run_once()
    assert row(database, 13)["removed_at"] is not None
    assert row(database, 10)["removed_at"] is None


def test_provider_error_is_recorded_without_raising(database: Database) -> None:
    class Broken:
        def things_with_xml(self, ids):
            raise RuntimeError("down")

    summary = worker(database, Broken()).run_once()
    assert summary["status"] == "error"
    assert "down" in get_sync_state(database, "worker_last_error")
