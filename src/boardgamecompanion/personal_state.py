from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from boardgamecompanion.database import Database


class PersonalStateError(ValueError):
    pass


class PersonalStateNotFound(PersonalStateError):
    pass


UNSET = object()


class PersonalStateStore:
    def __init__(self, database: Database):
        self.database = database

    def get(self, bgg_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT g.id AS board_game_id, g.bgg_id,
                       p.personal_rating, p.played_at, p.completed_at,
                       COALESCE(MAX(c.num_plays), 0) AS imported_num_plays
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                LEFT JOIN game_progress p ON p.board_game_id=g.id
                WHERE g.bgg_id=?
                GROUP BY g.id, g.bgg_id, p.personal_rating, p.played_at, p.completed_at
                """,
                (int(bgg_id),),
            ).fetchone()
        if row is None:
            raise PersonalStateNotFound(f"Board game BGG #{bgg_id} not found")
        completed_at = row["completed_at"]
        played_at = row["played_at"]
        imported_num_plays = int(row["imported_num_plays"] or 0)
        return {
            "bgg_id": int(row["bgg_id"]),
            "rating": (
                int(row["personal_rating"])
                if row["personal_rating"] is not None
                else None
            ),
            "played": bool(played_at or completed_at or imported_num_plays > 0),
            "played_at": played_at,
            "completed": bool(completed_at),
            "completed_at": completed_at,
            "imported_num_plays": imported_num_plays,
        }

    def update(
        self,
        bgg_id: int,
        *,
        rating: object = UNSET,
        played: object = UNSET,
        completed: object = UNSET,
        played_at: object = UNSET,
        completed_at: object = UNSET,
    ) -> dict[str, Any]:
        if rating is not UNSET and rating is not None:
            if type(rating) is not int or not 1 <= rating <= 5:
                raise PersonalStateError("rating must be an integer between 1 and 5")
        if played is not UNSET and type(played) is not bool:
            raise PersonalStateError("played must be boolean")
        if completed is not UNSET and type(completed) is not bool:
            raise PersonalStateError("completed must be boolean")
        if played is False and completed is True:
            raise PersonalStateError("a completed game must also be played")

        current = self.get(bgg_id)
        next_rating = current["rating"] if rating is UNSET else rating
        next_played_at = current["played_at"]
        next_completed_at = current["completed_at"]
        today = datetime.now(UTC).date().isoformat()

        if played_at is not UNSET:
            next_played_at = played_at
        if completed_at is not UNSET:
            next_completed_at = completed_at

        if played is True and not next_played_at:
            next_played_at = today
        elif played is False:
            next_played_at = None
            next_completed_at = None

        if completed is True:
            if not next_completed_at:
                next_completed_at = today
            if not next_played_at:
                next_played_at = next_completed_at
        elif completed is False:
            next_completed_at = None

        if next_completed_at and not next_played_at:
            next_played_at = next_completed_at

        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            game = connection.execute(
                "SELECT id FROM board_games WHERE bgg_id=?",
                (int(bgg_id),),
            ).fetchone()
            if game is None:
                raise PersonalStateNotFound(f"Board game BGG #{bgg_id} not found")
            connection.execute(
                """
                INSERT INTO game_progress(
                    board_game_id, played_at, completed_at, personal_rating,
                    created_at, updated_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(board_game_id) DO UPDATE SET
                    played_at=excluded.played_at,
                    completed_at=excluded.completed_at,
                    personal_rating=excluded.personal_rating,
                    updated_at=excluded.updated_at
                """,
                (
                    int(game["id"]),
                    next_played_at,
                    next_completed_at,
                    next_rating,
                    now,
                    now,
                ),
            )
        return self.get(bgg_id)
