from __future__ import annotations

import calendar
import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from boardgamecompanion.database import Database
from boardgamecompanion.personal_state import PersonalStateError, PersonalStateNotFound, _normalize_personal_date
from boardgamecompanion.players import PlayerProfiles, PlayerResolver, name_key
from boardgamecompanion.title_search import display_title, metadata_dict

OUTCOMES = {"won", "lost", "draw"}
STAT_PERIODS = ("day", "week", "month", "year", "all")
MAX_PLAYERS = 20
TEXT_LIMITS = {"activity": 500, "notes": 4000, "location": 120}


def suggested_play_mode(raw_metadata: Any) -> str | None:
    mechanics = metadata_dict(raw_metadata).get("mechanics")
    if not isinstance(mechanics, list) or not mechanics:
        return None
    names = {str(name).casefold() for name in mechanics}
    # Mixed/hidden-role games need the player to choose the variant actually played.
    if names & {"semi-cooperative game", "traitor game"}:
        return None
    return "cooperative" if "cooperative game" in names else "competitive"


def _player_won(play: dict[str, Any], player: dict[str, Any]) -> bool:
    if play["play_mode"] == "cooperative":
        return play["outcome"] == "won"
    return bool(player.get("winner"))


def _play_decided(play: dict[str, Any]) -> bool:
    if play["play_mode"] == "cooperative":
        return play["outcome"] is not None
    return any(player.get("winner") for player in play["players"]) or play["outcome"] is not None


def _month_start(value: date, shift: int = 0) -> date:
    index = value.year * 12 + value.month - 1 + shift
    return date(index // 12, index % 12 + 1, 1)


def _period_range(period: str, anchor: date, first: date) -> tuple[date, date]:
    if period == "day":
        return anchor, anchor
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = anchor.replace(day=1)
        return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])
    if period == "year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    return min(first, date.today()), date.today()


def _shift_anchor(period: str, start: date, step: int) -> date:
    if period == "day":
        return start + timedelta(days=step)
    if period == "week":
        return start + timedelta(days=7 * step)
    if period == "month":
        return _month_start(start, step)
    return date(start.year + step, 1, 1)


def _series_buckets(period: str, start: date, end: date) -> list[tuple[str, date, date]]:
    """Sotto-periodi del grafico: giorni per settimana/mese, mesi per anno (o «sempre» se breve)."""
    if period in {"week", "month"}:
        return [(d.isoformat(), d, d) for d in (start + timedelta(days=i) for i in range((end - start).days + 1))]
    if period == "year" or (period == "all" and (end.year * 12 + end.month) - (start.year * 12 + start.month) < 24):
        buckets = []
        month = start.replace(day=1)
        while month <= end:
            last = month.replace(day=calendar.monthrange(month.year, month.month)[1])
            buckets.append((month.isoformat()[:7], month, last))
            month = _month_start(month, 1)
        return buckets
    if period == "all":
        return [(str(year), date(year, 1, 1), date(year, 12, 31)) for year in range(start.year, end.year + 1)]
    return []


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
    """Una riga per partita; le sessioni collegano più partite e condividono la durata."""

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
            "title": display_title(row["title"], row["metadata_json"]),
            "has_cover": bool(row["cover_url"]),
            "played_on": row["played_on"],
            "player_count": row["player_count"],
            "players": players if isinstance(players, list) else [],
            "duration_minutes": row["duration_minutes"],
            "session_round": row["session_round"],
            "session": {
                "id": row["session_id"], "duration_minutes": row["session_duration_minutes"],
                "plays": row["session_plays"],
            } if row["session_id"] else None,
            "outcome": row["outcome"],
            "play_mode": row["play_mode"] or suggested_play_mode(row["metadata_json"]),
            "activity": row["activity"],
            "notes": row["notes"],
            "location": row["location"],
            "completed_game": bool(row["completed_game"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    _SELECT = """
        SELECT p.*, g.bgg_id, g.title, e.cover_url, e.metadata_json,
               s.duration_minutes AS session_duration_minutes,
               (SELECT COUNT(*) FROM game_plays sp WHERE sp.session_id=p.session_id) AS session_plays
        FROM game_plays p
        JOIN board_games g ON g.id=p.board_game_id
        LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
        LEFT JOIN play_sessions s ON s.id=p.session_id
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
        if "play_mode" in values:
            mode = values["play_mode"]
            if mode is not None and mode not in {"competitive", "cooperative"}:
                raise PlayError("play_mode must be competitive or cooperative")
            result["play_mode"] = mode
        for field in TEXT_LIMITS:
            if field in values:
                result[field] = _clean_text(values[field], field)
        if "completed_game" in values:
            if type(values["completed_game"]) is not bool:
                raise PlayError("completed_game must be boolean")
            result["completed_game"] = int(values["completed_game"])
        if "players_json" in result and "player_count" not in result:
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

    @staticmethod
    def _annotate(play: dict[str, Any], resolver: PlayerResolver) -> dict[str, Any]:
        """Collega ogni nome al profilo fisso corrispondente, senza cambiare il nome registrato."""
        for player in play["players"]:
            profile = resolver.resolve(player.get("name"))
            player["profile_id"] = profile["id"] if profile else None
        return play

    def get(self, play_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(self._SELECT + " WHERE p.id=?", (int(play_id),)).fetchone()
            resolver = PlayerProfiles(self.database).resolver(connection)
        if row is None:
            raise PlayNotFound(f"Play #{play_id} not found")
        return self._annotate(self._row(row), resolver)

    def create(self, bgg_id: int, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("session_duration_minutes") is not None:
            raise PlayError("use duration_minutes for a single play")
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

    def create_session(self, bgg_id: int, values: dict[str, Any]) -> dict[str, Any]:
        """Un solo salvataggio atomico; ritentare la stessa richiesta non duplica le partite."""
        request_id = values.get("request_id")
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
            raise PlayError("request_id must contain 32 lowercase hexadecimal characters")
        rounds = values.get("rounds")
        if not isinstance(rounds, list) or not 2 <= len(rounds) <= 20:
            raise PlayError("a session must contain between 2 and 20 plays")
        mode = values.get("play_mode")
        if mode not in {"competitive", "cooperative"}:
            raise PlayError("choose the session play_mode")
        common = self._validated(values, partial=False)
        duration = common.pop("duration_minutes", None)
        players = json.loads(common.get("players_json", "[]"))
        if any(not player["name"] for player in players):
            raise PlayError("session participants must have a name")
        if common.get("player_count") and common["player_count"] < len(players):
            raise PlayError("player_count cannot be less than the participants")
        data = []
        for index, round_values in enumerate(rounds):
            if not isinstance(round_values, dict):
                raise PlayError("each session play must be an object")
            winners = round_values.get("winner_indices") or []
            if (not isinstance(winners, list) or any(type(i) is not int or not 0 <= i < len(players) for i in winners)
                    or len(set(winners)) != len(winners)):
                raise PlayError("winner_indices must identify distinct session participants")
            outcome = round_values.get("outcome")
            if (mode == "cooperative" and winners) or (mode == "competitive" and outcome):
                raise PlayError("use individual winners for competitive games or a group outcome for cooperative games")
            scores = round_values.get("scores")
            if scores is None:
                scores = [None] * len(players)
            if not isinstance(scores, list) or len(scores) != len(players):
                raise PlayError("scores must match the session participants")
            participants = _clean_players([
                {"name": player["name"], "score": scores[i], "winner": i in winners}
                for i, player in enumerate(players)
            ])
            clean_outcome = self._validated({"outcome": outcome}, partial=True)["outcome"]
            data.append({**common, "duration_minutes": None,
                         "players_json": json.dumps(participants, ensure_ascii=False), "outcome": clean_outcome,
                         "completed_game": common.get("completed_game", 0) if index == len(rounds) - 1 else 0,
                         "session_id": request_id, "session_round": index + 1})
        fingerprint = json.dumps({"bgg_id": bgg_id, "duration_minutes": duration, "plays": data},
                                 ensure_ascii=False, sort_keys=True)
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            game_id = self._game_id(connection, bgg_id)
            existing = connection.execute("SELECT request_json FROM play_sessions WHERE id=?", (request_id,)).fetchone()
            if existing:
                if existing["request_json"] != fingerprint:
                    raise PlayError("request_id was already used for a different session; reopen the form")
            else:
                connection.execute(
                    "INSERT INTO play_sessions(id,board_game_id,duration_minutes,request_json,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?)", (request_id, game_id, duration, fingerprint, now, now),
                )
                for play in data:
                    columns = ["board_game_id", *play, "created_at", "updated_at"]
                    connection.execute(
                        f"INSERT INTO game_plays({','.join(columns)}) VALUES({','.join('?' * len(columns))})",
                        (game_id, *play.values(), now, now),
                    )
                self._sync_progress(connection, game_id, now)
            rows = connection.execute(self._SELECT + " WHERE p.session_id=? ORDER BY p.session_round", (request_id,)).fetchall()
            resolver = PlayerProfiles(self.database).resolver(connection)
        return {"session_id": request_id, "items": [self._annotate(self._row(row), resolver) for row in rows]}

    def update(self, play_id: int, values: dict[str, Any]) -> dict[str, Any]:
        data = self._validated(values, partial=True)
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT board_game_id,session_id FROM game_plays WHERE id=?", (int(play_id),)).fetchone()
            if row is None:
                raise PlayNotFound(f"Play #{play_id} not found")
            if row["session_id"] and data.get("duration_minutes") is not None:
                raise PlayError("use session_duration_minutes for a session")
            if "session_duration_minutes" in values:
                if not row["session_id"]:
                    raise PlayError("this play does not belong to a session")
                duration = _optional_int(values["session_duration_minutes"], "session_duration_minutes", 1, 10000)
                connection.execute("UPDATE play_sessions SET duration_minutes=?,updated_at=? WHERE id=?",
                                   (duration, now, row["session_id"]))
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
        player_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        profiles = PlayerProfiles(self.database)
        resolver = profiles.resolver()
        if player_id is not None:
            keys = sorted(resolver.keys_for(player_id))
            if not keys:
                return {"items": [], "total": 0}
            where.append(
                "EXISTS (SELECT 1 FROM json_each(p.players_json) j "
                f"WHERE bgc_name_key(json_extract(j.value,'$.name')) IN ({','.join('?' * len(keys))}))"
            )
            params.extend(keys)
        if date_from:
            where.append("p.played_on>=?")
            params.append(date_from)
        if date_to:
            where.append("p.played_on<=?")
            params.append(date_to)
        if bgg_id is not None:
            where.append("g.bgg_id=?")
            params.append(int(bgg_id))
        if player:
            # Un nome che appartiene a un profilo cerca anche gli alias dello stesso profilo.
            profile = resolver.resolve(player)
            keys = sorted(resolver.keys_for(profile["id"])) if profile else [name_key(player)]
            where.append(
                "EXISTS (SELECT 1 FROM json_each(p.players_json) j "
                f"WHERE bgc_name_key(json_extract(j.value,'$.name')) IN ({','.join('?' * len(keys))}))"
            )
            params.extend(keys)
        if q:
            like = f"%{q.strip()}%"
            where.append(
                "(g.title LIKE ? OR p.activity LIKE ? OR p.notes LIKE ? OR p.location LIKE ? OR p.players_json LIKE ? "
                "OR json_extract(e.metadata_json,'$.alternate_titles') LIKE ? "
                "OR json_extract(e.metadata_json,'$.italian_title') LIKE ?)"
            )
            params.extend([like] * 7)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.database.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM game_plays p JOIN board_games g ON g.id=p.board_game_id "
                f"LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id {clause}",
                params,
            ).fetchone()[0]
            rows = connection.execute(
                self._SELECT + f" {clause} ORDER BY p.played_on DESC, p.id DESC LIMIT ? OFFSET ?",
                (*params, max(1, min(int(limit), 200)), max(0, int(offset))),
            ).fetchall()
        return {"items": [self._annotate(self._row(row), resolver) for row in rows], "total": int(total)}

    def defaults(self, bgg_id: int | None = None) -> dict[str, Any]:
        """What a new play can copy: the last play of this game, else the last play overall."""
        with self.database.connect() as connection:
            game = connection.execute(
                "SELECT e.metadata_json FROM board_games g "
                "LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id WHERE g.bgg_id=?",
                (bgg_id,),
            ).fetchone() if bgg_id is not None else None
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
                SELECT location, COUNT(*) AS plays FROM game_plays WHERE COALESCE(location,'') != ''
                GROUP BY lower(location) ORDER BY plays DESC, MAX(played_on) DESC LIMIT 12
                """
            ).fetchall()
            profiles = PlayerProfiles(self.database).list(connection)
        resolver = PlayerResolver(profiles)
        last = self._annotate(self._row(row), resolver) if row is not None else None
        return {
            "last_play": last,
            "same_game": same_game,
            "player_names": [item["name"] for item in names],
            "guest_names": [item["name"] for item in names if resolver.resolve(item["name"]) is None],
            "profiles": profiles,
            "locations": [item["location"] for item in locations],
            "suggested_mode": suggested_play_mode(game["metadata_json"]) if game else None,
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
            session_minutes = connection.execute(
                "SELECT COALESCE(SUM(s.duration_minutes),0) FROM play_sessions s "
                "WHERE EXISTS(SELECT 1 FROM game_plays p WHERE p.session_id=s.id)"
            ).fetchone()[0]
            months = connection.execute(
                """
                SELECT substr(played_on,1,7) AS month, COUNT(*) AS plays
                FROM game_plays WHERE played_on >= ?
                GROUP BY month ORDER BY month
                """,
                (date(today.year - 1, today.month, 1).isoformat(),),
            ).fetchall()
            resolver = PlayerProfiles(self.database).resolver(connection)
            player_totals: dict[str, dict[str, Any]] = {}
            for session in connection.execute(self._SELECT):
                play = self._row(session)
                for player in play["players"]:
                    name = player.get("name") or ""
                    if not name:
                        continue
                    profile = resolver.resolve(name)
                    key = f"profile:{profile['id']}" if profile else name.casefold()
                    entry = player_totals.setdefault(key, {"name": profile["name"] if profile else name,
                                                           "profile_id": profile["id"] if profile else None,
                                                           "plays": 0, "wins": 0})
                    if not profile:
                        entry["name"] = min(entry["name"], name)
                    entry["plays"] += 1
                    entry["wins"] += int(_player_won(play, player))
            players = sorted(player_totals.values(), key=lambda item: (-item["plays"], -item["wins"]))[:12]
            games = connection.execute(
                """
                SELECT g.bgg_id, g.title, e.cover_url, e.metadata_json, COUNT(p.id) AS plays,
                       MAX(p.played_on) AS last_played_on,
                       COALESCE(SUM(p.duration_minutes),0) + (
                           SELECT COALESCE(SUM(s.duration_minutes),0) FROM play_sessions s
                           WHERE s.board_game_id=g.id AND EXISTS(SELECT 1 FROM game_plays sp WHERE sp.session_id=s.id)
                       ) AS minutes,
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
            "minutes": int(totals["minutes"] or 0) + int(session_minutes),
            "last_played_on": totals["last_played_on"],
            "months": [dict(row) for row in months],
            "players": players,
            "games_played": [
                {
                    "bgg_id": int(row["bgg_id"]),
                    "title": display_title(row["title"], row["metadata_json"]),
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

    def _stat_plays(self, connection: Any, start: str | None, end: str | None) -> list[dict[str, Any]]:
        where, params = [], []
        if start:
            where.append("p.played_on>=?")
            params.append(start)
        if end:
            where.append("p.played_on<=?")
            params.append(end)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        plays = []
        for row in connection.execute(self._SELECT + clause + " ORDER BY p.played_on, p.id", params):
            play = self._row(row)
            # Una sessione conta la sua durata una sola volta: si divide fra le partite che la compongono.
            if play["session"]:
                total = play["session"]["duration_minutes"] or 0
                play["minutes"] = total / max(1, int(play["session"]["plays"] or 1))
            else:
                play["minutes"] = play["duration_minutes"] or 0
            plays.append(play)
        return plays

    @staticmethod
    def _aggregate(plays: list[dict[str, Any]], resolver: PlayerResolver, focus: set[str] | None) -> dict[str, Any]:
        games: dict[int, dict[str, Any]] = {}
        players: dict[str, dict[str, Any]] = {}
        companions: dict[str, dict[str, Any]] = {}
        locations: dict[str, dict[str, Any]] = {}
        days: set[str] = set()
        totals = {"plays": 0, "minutes": 0.0, "wins": 0, "decided": 0}
        for play in plays:
            names = [player for player in play["players"] if player.get("name")]
            me = next((player for player in names if name_key(player["name"]) in focus), None) if focus else None
            if focus and me is None:
                continue
            won = _player_won(play, me) if me else False
            totals["plays"] += 1
            totals["minutes"] += play["minutes"]
            if me and _play_decided(play):
                totals["decided"] += 1
                totals["wins"] += int(won)
            days.add(play["played_on"])
            game = games.setdefault(play["bgg_id"], {
                "bgg_id": play["bgg_id"], "title": play["title"], "has_cover": play["has_cover"],
                "plays": 0, "minutes": 0.0, "wins": 0, "last_played_on": play["played_on"]})
            game["plays"] += 1
            game["minutes"] += play["minutes"]
            game["wins"] += int(won)
            game["last_played_on"] = max(game["last_played_on"], play["played_on"])
            if play["location"]:
                place = locations.setdefault(play["location"].casefold(), {"name": play["location"], "plays": 0})
                place["plays"] += 1
            for player in names:
                profile = resolver.resolve(player["name"])
                key = f"profile:{profile['id']}" if profile else name_key(player["name"])
                entry = players.setdefault(key, {
                    "name": profile["name"] if profile else player["name"],
                    "profile_id": profile["id"] if profile else None,
                    "plays": 0, "wins": 0, "minutes": 0.0})
                entry["plays"] += 1
                entry["wins"] += int(_player_won(play, player))
                entry["minutes"] += play["minutes"]
                if me is not None and player is not me:
                    mate = companions.setdefault(key, {"name": entry["name"], "profile_id": entry["profile_id"], "plays": 0})
                    mate["plays"] += 1

        def ranked(items: dict[str, Any] | dict[int, Any], *keys: str) -> list[dict[str, Any]]:
            result = sorted(items.values(), key=lambda item: tuple(-item[key] for key in keys))
            for item in result:
                if "minutes" in item:
                    item["minutes"] = round(item["minutes"])
            return result

        return {
            "totals": {"plays": totals["plays"], "minutes": round(totals["minutes"]), "games": len(games),
                       "days": len(days), "players": len(players), "wins": totals["wins"],
                       "decided": totals["decided"]},
            "games": ranked(games, "plays", "minutes"),
            "players": ranked(players, "plays", "wins"),
            "companions": ranked(companions, "plays"),
            "locations": ranked(locations, "plays"),
        }

    def stats(
        self,
        *,
        period: str = "month",
        anchor: str | None = None,
        player_id: int | None = None,
        player: str | None = None,
    ) -> dict[str, Any]:
        """Statistiche di un giorno, settimana (lun–dom), mese, anno o di tutto lo storico."""
        if period not in STAT_PERIODS:
            raise PlayError("period must be day, week, month, year or all")
        try:
            anchor_date = date.fromisoformat(anchor) if anchor else date.today()
        except ValueError as exc:
            raise PlayError("anchor must be a date") from exc
        with self.database.connect() as connection:
            resolver = PlayerProfiles(self.database).resolver(connection)
            first_row = connection.execute("SELECT MIN(played_on) FROM game_plays").fetchone()[0]
            first = date.fromisoformat(first_row) if first_row else date.today()
            start, end = _period_range(period, anchor_date, first)
            focus: set[str] | None = None
            if player_id is not None:
                focus = resolver.keys_for(player_id)
                if not focus:
                    raise PlayNotFound(f"Player #{player_id} not found")
            elif player:
                profile = resolver.resolve(player)
                focus = resolver.keys_for(profile["id"]) if profile else {name_key(player)}
            plays = self._stat_plays(connection, start.isoformat(), end.isoformat())
            previous = None
            prev_anchor = next_anchor = None
            if period != "all":
                prev_anchor = _shift_anchor(period, start, -1)
                prev_start, prev_end = _period_range(period, prev_anchor, first)
                previous = self._aggregate(
                    self._stat_plays(connection, prev_start.isoformat(), prev_end.isoformat()), resolver, focus
                )["totals"]
                if prev_end < first:
                    prev_anchor = None
                next_anchor = _shift_anchor(period, start, 1)
                if next_anchor > date.today():
                    next_anchor = None
        result = self._aggregate(plays, resolver, focus)
        series = []
        for key, bucket_start, bucket_end in _series_buckets(period, start, end):
            low, high = bucket_start.isoformat(), bucket_end.isoformat()
            subset = [play for play in plays if low <= play["played_on"] <= high]
            bucket = self._aggregate(subset, resolver, focus)["totals"] if subset else {"plays": 0, "minutes": 0}
            series.append({"key": key, "start": low, "end": high, "plays": bucket["plays"], "minutes": bucket["minutes"]})
        return {
            "period": period,
            "anchor": anchor_date.isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "prev_anchor": prev_anchor.isoformat() if prev_anchor else None,
            "next_anchor": next_anchor.isoformat() if next_anchor else None,
            "first_played_on": first_row,
            "previous": previous,
            "series": series,
            **result,
        }

    def player_overview(self, player_id: int) -> dict[str, Any]:
        """Profilo con le statistiche di tutto lo storico del giocatore."""
        profile = PlayerProfiles(self.database).get(player_id)
        stats = self.stats(period="all", player_id=player_id)
        with self.database.connect() as connection:
            keys = sorted(PlayerProfiles(self.database).resolver(connection).keys_for(player_id))
            row = connection.execute(
                "SELECT MIN(p.played_on) AS first, MAX(p.played_on) AS last FROM game_plays p "
                "WHERE EXISTS (SELECT 1 FROM json_each(p.players_json) j "
                f"WHERE bgc_name_key(json_extract(j.value,'$.name')) IN ({','.join('?' * len(keys))}))",
                keys,
            ).fetchone()
        return {"profile": profile, "first_played_on": row["first"], "last_played_on": row["last"],
                "totals": stats["totals"], "games": stats["games"], "companions": stats["companions"],
                "locations": stats["locations"]}
