from __future__ import annotations

from datetime import UTC, datetime, timedelta

from boardgamecompanion.database import Database
from boardgamecompanion.rate_limits import PersistentRateLimiter


def test_rate_limit_is_shared_by_fresh_instances_and_persisted(tmp_path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.initialize()
    current = [datetime(2026, 9, 27, tzinfo=UTC)]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        current[0] += timedelta(seconds=seconds)

    first = PersistentRateLimiter(database, sleep=sleep, now=lambda: current[0])
    second = PersistentRateLimiter(database, sleep=sleep, now=lambda: current[0])
    first.acquire("provider:test", 5)
    second.acquire("provider:test", 5)

    assert sleeps == [5.0]
    with database.connect() as connection:
        row = connection.execute(
            "SELECT next_allowed_at FROM external_request_limits WHERE scope='provider:test'"
        ).fetchone()
    assert row["next_allowed_at"] == datetime(2026, 9, 27, 0, 0, 10, tzinfo=UTC).isoformat()
