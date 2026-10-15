from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from boardgamecompanion.database import Database


class PersonalGameError(ValueError):
    pass


_UNSET = object()


class PersonalGameService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _game_id(self, connection, bgg_id: int) -> int:
        row = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id=?",
            (int(bgg_id),),
        ).fetchone()
        if row is None:
            raise PersonalGameError("Board game not found")
        return int(row["id"])

    def get(self, bgg_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            game_id = self._game_id(connection, bgg_id)
            row = connection.execute(
                """
                SELECT p.personal_rating,p.played_at,p.completed_at,
                       COALESCE(c.num_plays,0) AS imported_plays
                FROM board_games g
                LEFT JOIN game_progress p ON p.board_game_id=g.id
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                WHERE g.id=?
                ORDER BY c.id
                LIMIT 1
                """,
                (game_id,),
            ).fetchone()
        explicit_played = bool(row["played_at"]) if row else False
        imported_plays = int(row["imported_plays"] or 0) if row else 0
        completed = bool(row["completed_at"]) if row else False
        return {
            "bgg_id": int(bgg_id),
            "rating": int(row["personal_rating"]) if row and row["personal_rating"] is not None else None,
            "played": explicit_played or imported_plays > 0 or completed,
            "played_at": row["played_at"] if row else None,
            "completed": completed,
            "completed_at": row["completed_at"] if row else None,
            "imported_plays": imported_plays,
        }

    def update(
        self,
        bgg_id: int,
        *,
        rating: int | None | object = _UNSET,
        played: bool | object = _UNSET,
        played_at: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        if rating is not _UNSET and rating is not None and not 1 <= int(rating) <= 5:
            raise PersonalGameError("Personal rating must be between 1 and 5")
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        today = now.date().isoformat()

        with self.database.transaction(immediate=True) as connection:
            game_id = self._game_id(connection, bgg_id)
            current = connection.execute(
                "SELECT * FROM game_progress WHERE board_game_id=?",
                (game_id,),
            ).fetchone()
            current_rating = current["personal_rating"] if current else None
            current_played_at = current["played_at"] if current else None
            current_completed_at = current["completed_at"] if current else None

            new_rating = current_rating if rating is _UNSET else rating
            new_played_at = current_played_at
            if played is not _UNSET:
                if bool(played):
                    new_played_at = (
                        played_at
                        if played_at is not _UNSET and played_at
                        else current_played_at or today
                    )
                else:
                    new_played_at = None
            elif played_at is not _UNSET:
                new_played_at = played_at

            if new_rating is None and new_played_at is None and current_completed_at is None:
                connection.execute(
                    "DELETE FROM game_progress WHERE board_game_id=?",
                    (game_id,),
                )
            else:
                created_at = current["created_at"] if current else now_iso
                connection.execute(
                    """
                    INSERT INTO game_progress(
                        board_game_id,completed_at,played_at,personal_rating,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(board_game_id) DO UPDATE SET
                        played_at=excluded.played_at,
                        personal_rating=excluded.personal_rating,
                        updated_at=excluded.updated_at
                    """,
                    (
                        game_id,
                        current_completed_at,
                        new_played_at,
                        new_rating,
                        created_at,
                        now_iso,
                    ),
                )
        return self.get(bgg_id)
