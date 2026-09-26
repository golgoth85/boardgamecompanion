from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Callable

from boardgamecompanion.database import Database


class PersistentRateLimiter:
    """Cross-thread/process fixed-interval gate persisted in SQLite."""

    def __init__(
        self,
        database: Database,
        *,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(UTC))

    def acquire(self, scope: str, min_interval_seconds: float) -> None:
        interval = float(min_interval_seconds)
        if interval <= 0:
            return
        normalized_scope = str(scope).strip()
        if not normalized_scope or len(normalized_scope) > 200:
            raise ValueError("Invalid rate-limit scope")
        while True:
            current = self._now().astimezone(UTC)
            with self.database.transaction(immediate=True) as connection:
                row = connection.execute(
                    "SELECT next_allowed_at FROM external_request_limits WHERE scope=?",
                    (normalized_scope,),
                ).fetchone()
                due = (
                    datetime.fromisoformat(row["next_allowed_at"]).astimezone(UTC)
                    if row is not None
                    else current
                )
                if due <= current:
                    next_allowed = current + timedelta(seconds=interval)
                    connection.execute(
                        """INSERT INTO external_request_limits(scope,next_allowed_at,updated_at)
                           VALUES (?,?,?) ON CONFLICT(scope) DO UPDATE SET
                           next_allowed_at=excluded.next_allowed_at,
                           updated_at=excluded.updated_at""",
                        (normalized_scope, next_allowed.isoformat(), current.isoformat()),
                    )
                    return
            self._sleep(min(max((due - current).total_seconds(), 0.001), interval))

