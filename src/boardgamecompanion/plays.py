from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from boardgamecompanion.database import Database
from boardgamecompanion.personal_state import PersonalStateError, PersonalStateNotFound, _normalize_personal_date

OUTCOMES = {"won", "lost", "draw"}
MAX_PLAYERS = 20
TEXT_LIMITS = {"activity": 500, "notes": 4000, "location": 120}


class PlayError(PersonalStateError):
    pass


class PlayNotFound(PersonalStateNotFound):
    pass


def _clean_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlayError(f"{field} must be text")
    text = value.strip()
    if len(text) > TEXT_LIMITS[field]:
        raise PlayError(f"{field} is too long")
    return text or None


def _clean_players(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_PLAYERS:
        raise PlayError(f"players must be a list of at most {MAX_PLAYERS} entries")
    players: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise PlayError("each player must be an object")
        name = str(raw.get("name") or "").strip()[:60]
        score = raw.get("score")
        score = str(score).strip()[:20] if score not in (None, "") else None
        winner = raw.get("winner") is True
        if not name and score is None and not winner:
            continue
        players.append({"name": name, "score": score, "winner": winner})
    return players


def _optional_int(value: Any, field: str, low: int, high: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not low <= value <= high:
        raise PlayError(f"{field} must be between {low} and {high}")
    return value


class PlayLog:
    """Sessions played, one row each; keeps game_progress in step."""

    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        try:
            players = json.loads(row["players_json"] or "[]")
        except ValueError:
            players = []
        return {
            "id": int(row["id"]),
            "bgg_id": int(row["bgg_id"]),
            "title": row["title"],
            "has_cover": bool(row["cover_url"]),
            "played_on": row["played_on"],
            "player_count": row["player_count"],
            "players": players if isinstance(players, list) else [],
            "duration_minutes": row["duration_minutes"],
            "outcome": row["outcome"],
            "activity": row["activity"],
            "notes": row["notes"],
            "location": row["location"],
            "completed_game": bool(row["completed_game"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    _SELECT = """
        SELECT p.*, g.bgg_id, g.title, e.cover_url
        FROM game_plays p
        JOIN board_games g ON g.id=p.board_game_id
        LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
    """

    def _validated(self, values: dict[str, Any], *, partial: bool) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if "played_on" in values or not partial:
            try:
                played_on = _normalize_personal_date(values.get("played_on"), "played_on")
            except PersonalStateError as exc:
                raise PlayError(str(exc)) from exc
            if played_on is None:
                raise PlayError("played_on is required")
            result["played_on"] = played_on
        if "players" in values:
            result["players_json"] = json.dumps(_clean_players(values["players"]), ensure_ascii=False)
        if "player_count" in values:
            result["player_count"] = _optional_int(values["player_count"], "player_count", 1, 99)
        if "duration_minutes" in values:
            result["duration_minutes"] = _optional_int(values["duration_minutes"], "duration_minutes", 1, 10000)
        if "outcome" in values:
            outcome = values["outcome"] or None
            if outcome is not None and outcome not in OUTCOMES:
                raise PlayError("outcome must be won, lost or draw")
            result["outcome"] = outcome
        for field in TEXT_LIMITS:
            if field in values:
                result[field] = _clean_text(values[field], field)
        if "completed_game" in values:
            if type(values["completed_game"]) is not bool:
                raise PlayError("completed_game must be boolean")
            result["completed_game"] = int(values["completed_game"])
        if "players_json" in result and "player_count" not in result and not partial:
            named = len(json.loads(result["players_json"]))
            result["player_count"] = named or None
        return result

    @staticmethod
    def _sync_progress(connection: Any, board_game_id: int, now: str) -> None:
        """A logged play marks the game as played; a completing play completes it."""
        latest = connection.execute(
            "SELECT MAX(played_on) AS latest FROM game_plays WHERE board_game_id=?",
            (board_game_id,),
        ).fetchone()["latest"]
        completed = connection.execute(
            "SELECT MIN(played_on) AS first FROM game_plays WHERE board_game_id=? AND completed_game=1",
            (board_game_id,),
        ).fetchone()["first"]
        if not latest:
            return
        connection.execute(
            """
            INSERT INTO game_progress(board_game_id, played_at, completed_at, created_at, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(board_game_id) DO UPDATE SET
                played_at=CASE WHEN game_progress.played_at IS NULL OR game_progress.played_at < excluded.played_at
                               THEN excluded.played_at ELSE game_progress.played_at END,
                completed_at=COALESCE(game_progress.completed_at, excluded.completed_at),
                updated_at=excluded.updated_at
            """,
            (board_game_id, latest, completed, now, now),
        )

    def _game_id(self, connection: Any, bgg_id: int) -> int:
        row = connection.execute("SELECT id FROM board_games WHERE bgg_id=?", (int(bgg_id),)).fetchone()
        if row is None:
            raise PlayNotFound(f"Board game BGG #{bgg_id} not found")
        return int(row["id"])

    def get(self, play_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(self._SELECT + " WHERE p.id=?", (int(play_id),)).fetchone()
        if row is None:
            raise PlayNotFound(f"Play #{play_id} not found")
        return self._row(row)

    def create(self, bgg_id: int, values: dict[str, Any]) -> dict[str, Any]:
        data = self._validated(values, partial=False)
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            game_id = self._game_id(connection, bgg_id)
            columns = ["board_game_id", *data, "created_at", "updated_at"]
            cursor = connection.execute(
                f"INSERT INTO game_plays({','.join(columns)}) VALUES({','.join('?' * len(columns))})",
                (game_id, *data.values(), now, now),
            )
            self._sync_progress(connection, game_id, now)
            play_id = int(cursor.lastrowid)
        return self.get(play_id)

    def update(self, play_id: int, values: dict[str, Any]) -> dict[str, Any]:
        data = self._validated(values, partial=True)
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT board_game_id FROM game_plays WHERE id=?", (int(play_id),)).fetchone()
            if row is None:
                raise PlayNotFound(f"Play #{play_id} not found")
            if data:
                assignments = ",".join(f"{column}=?" for column in data)
                connection.execute(
                    f"UPDATE game_plays SET {assignments}, updated_at=? WHERE id=?",
                    (*data.values(), now, int(play_id)),
                )
            self._sync_progress(connection, int(row["board_game_id"]), now)
        return self.get(play_id)

    def delete(self, play_id: int) -> None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT board_game_id, played_on FROM game_plays WHERE id=?", (int(play_id),)
            ).fetchone()
            if row is None:
                raise PlayNotFound(f"Play #{play_id} not found")
            connection.execute("DELETE FROM game_plays WHERE id=?", (int(play_id),))
            # The last played date follows the remaining plays; a date set by hand
            # (or with no plays left) stays as it is.
            connection.execute(
                """
                UPDATE game_progress SET
                    played_at=(SELECT MAX(played_on) FROM game_plays WHERE board_game_id=?),
                    updated_at=?
                WHERE board_game_id=? AND played_at=?
                  AND EXISTS (SELECT 1 FROM game_plays WHERE board_game_id=?)
                """,
                (row["board_game_id"], datetime.now(UTC).isoformat(), row["board_game_id"],
                 row["played_on"], row["board_game_id"]),
            )

    def list(
        self,
        *,
        bgg_id: int | None = None,
        player: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if bgg_id is not None:
            where.append("g.bgg_id=?")
            params.append(int(bgg_id))
        if player:
            where.append(
                "EXISTS (SELECT 1 FROM json_each(p.players_json) j "
                "WHERE lower(json_extract(j.value,'$.name'))=lower(?))"
            )
            params.append(player.strip())
        if q:
            like = f"%{q.strip()}%"
            where.append(
                "(g.title LIKE ? OR p.activity LIKE ? OR p.notes LIKE ? OR p.location LIKE ? OR p.players_json LIKE ?)"
            )
            params.extend([like] * 5)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.database.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM game_plays p JOIN board_games g ON g.id=p.board_game_id {clause}",
                params,
            ).fetchone()[0]
            rows = connection.execute(
                self._SELECT + f" {clause} ORDER BY p.played_on DESC, p.id DESC LIMIT ? OFFSET ?",
                (*params, max(1, min(int(limit), 200)), max(0, int(offset))),
            ).fetchall()
        return {"items": [self._row(row) for row in rows], "total": int(total)}

    def defaults(self, bgg_id: int | None = None) -> dict[str, Any]:
        """What a new play can copy: the last play of this game, else the last play overall."""
        with self.database.connect() as connection:
            row = None
            if bgg_id is not None:
                row = connection.execute(
                    self._SELECT + " WHERE g.bgg_id=? ORDER BY p.played_on DESC, p.id DESC LIMIT 1",
                    (int(bgg_id),),
                ).fetchone()
            same_game = row is not None
            if row is None:
                row = connection.execute(
                    self._SELECT + " ORDER BY p.played_on DESC, p.id DESC LIMIT 1"
                ).fetchone()
            names = connection.execute(
                """
                SELECT json_extract(j.value,'$.name') AS name, COUNT(*) AS plays,
                       MAX(p.played_on) AS last
                FROM game_plays p, json_each(p.players_json) j
                WHERE COALESCE(json_extract(j.value,'$.name'),'') != ''
                GROUP BY lower(json_extract(j.value,'$.name'))
                ORDER BY plays DESC, last DESC
                LIMIT 40
                """
            ).fetchall()
            locations = connection.execute(
                """
                SELECT location FROM game_plays WHERE COALESCE(location,'') != ''
                GROUP BY lower(location) ORDER BY MAX(played_on) DESC LIMIT 10
                """
            ).fetchall()
        last = self._row(row) if row is not None else None
        return {
            "last_play": last,
            "same_game": same_game,
            "player_names": [item["name"] for item in names],
            "locations": [item["location"] for item in locations],
        }

    def summary(self) -> dict[str, Any]:
        today = date.today()
        with self.database.connect() as connection:
            totals = connection.execute(
                """
                SELECT COUNT(*) AS plays, COUNT(DISTINCT board_game_id) AS games,
                       SUM(CASE WHEN substr(played_on,1,4)=? THEN 1 ELSE 0 END) AS this_year,
                       COALESCE(SUM(duration_minutes),0) AS minutes,
                       MAX(played_on) AS last_played_on
                FROM game_plays
                """,
                (str(today.year),),
            ).fetchone()
            months = connection.execute(
                """
                SELECT substr(played_on,1,7) AS month, COUNT(*) AS plays
                FROM game_plays WHERE played_on >= ?
                GROUP BY month ORDER BY month
                """,
                (date(today.year - 1, today.month, 1).isoformat(),),
            ).fetchall()
            players = connection.execute(
                """
                SELECT MIN(json_extract(j.value,'$.name')) AS name, COUNT(*) AS plays,
                       SUM(CASE WHEN json_extract(j.value,'$.winner') THEN 1 ELSE 0 END) AS wins
                FROM game_plays p, json_each(p.players_json) j
                WHERE COALESCE(json_extract(j.value,'$.name'),'') != ''
                GROUP BY lower(json_extract(j.value,'$.name'))
                ORDER BY plays DESC, wins DESC LIMIT 8
                """
            ).fetchall()
            games = connection.execute(
                """
                SELECT g.bgg_id, g.title, e.cover_url, COUNT(p.id) AS plays,
                       MAX(p.played_on) AS last_played_on,
                       COALESCE(SUM(p.duration_minutes),0) AS minutes,
                       SUM(CASE WHEN p.outcome='won' THEN 1 ELSE 0 END) AS won,
                       SUM(CASE WHEN p.outcome='lost' THEN 1 ELSE 0 END) AS lost
                FROM game_plays p
                JOIN board_games g ON g.id=p.board_game_id
                LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
                GROUP BY g.id ORDER BY plays DESC, last_played_on DESC
                """
            ).fetchall()
        return {
            "plays": int(totals["plays"] or 0),
            "games": int(totals["games"] or 0),
            "this_year": int(totals["this_year"] or 0),
            "minutes": int(totals["minutes"] or 0),
            "last_played_on": totals["last_played_on"],
            "months": [dict(row) for row in months],
            "players": [
                {"name": row["name"], "plays": int(row["plays"]), "wins": int(row["wins"] or 0)}
                for row in players
            ],
            "games_played": [
                {
                    "bgg_id": int(row["bgg_id"]),
                    "title": row["title"],
                    "has_cover": bool(row["cover_url"]),
                    "plays": int(row["plays"]),
                    "last_played_on": row["last_played_on"],
                    "minutes": int(row["minutes"] or 0),
                    "won": int(row["won"] or 0),
                    "lost": int(row["lost"] or 0),
                }
                for row in games
            ],
        }
