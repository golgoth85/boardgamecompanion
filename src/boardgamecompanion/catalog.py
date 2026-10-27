from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from typing import Any

from boardgamecompanion.database import Database
from boardgamecompanion.explore_groups import group_definitions, group_key, valid_group_keys
from boardgamecompanion.title_search import game_title_terms, title_query_matches


SORT_SQL = {
    "title": "g.title COLLATE NOCASE ASC, g.bgg_id ASC",
    "title_desc": "g.title COLLATE NOCASE DESC, g.bgg_id DESC",
    "players_asc": (
        "g.min_players IS NULL, g.min_players ASC, "
        "g.max_players IS NULL, g.max_players ASC, g.title COLLATE NOCASE ASC"
    ),
    "players_desc": (
        "g.min_players IS NULL, g.min_players DESC, "
        "g.max_players IS NULL, g.max_players DESC, g.title COLLATE NOCASE ASC"
    ),
    "age_asc": (
        "g.bgg_recommended_age IS NULL OR CAST(g.bgg_recommended_age AS INTEGER) = 0, "
        "CAST(g.bgg_recommended_age AS INTEGER) ASC, g.title COLLATE NOCASE ASC"
    ),
    "age_desc": (
        "g.bgg_recommended_age IS NULL OR CAST(g.bgg_recommended_age AS INTEGER) = 0, "
        "CAST(g.bgg_recommended_age AS INTEGER) DESC, g.title COLLATE NOCASE ASC"
    ),
    "duration_asc": (
        "COALESCE(g.playing_time, g.max_play_time, g.min_play_time) IS NULL, "
        "COALESCE(g.playing_time, g.max_play_time, g.min_play_time) ASC, "
        "g.title COLLATE NOCASE ASC"
    ),
    "duration_desc": (
        "COALESCE(g.playing_time, g.max_play_time, g.min_play_time) IS NULL, "
        "COALESCE(g.playing_time, g.max_play_time, g.min_play_time) DESC, "
        "g.title COLLATE NOCASE ASC"
    ),
    "year_desc": "g.year_published IS NULL, g.year_published DESC, g.title COLLATE NOCASE ASC",
    "rating_desc": "g.bgg_average IS NULL, g.bgg_average DESC, g.title COLLATE NOCASE ASC",
    "rating_asc": "g.bgg_average IS NULL, g.bgg_average ASC, g.title COLLATE NOCASE ASC",
    "rank_asc": "g.bgg_rank IS NULL OR g.bgg_rank = 0, g.bgg_rank ASC, g.title COLLATE NOCASE ASC",
    "weight_desc": "g.bgg_average_weight IS NULL, g.bgg_average_weight DESC, g.title COLLATE NOCASE ASC",
    "weight_asc": "g.bgg_average_weight IS NULL, g.bgg_average_weight ASC, g.title COLLATE NOCASE ASC",
    "acquired_desc": (
        "COALESCE(NULLIF(c.acquisition_date,''),c.first_seen_at) IS NULL, "
        "COALESCE(NULLIF(c.acquisition_date,''),c.first_seen_at) DESC, "
        "g.title COLLATE NOCASE ASC"
    ),
    "completed_desc": (
        "p.completed_at IS NULL, p.completed_at DESC, g.title COLLATE NOCASE ASC"
    ),
    "played_desc": (
        "COALESCE(p.played_at,p.completed_at) IS NULL, "
        "COALESCE(p.played_at,p.completed_at) DESC, g.title COLLATE NOCASE ASC"
    ),
    "personal_rating_desc": (
        "p.personal_rating IS NULL, p.personal_rating DESC, g.title COLLATE NOCASE ASC"
    ),
}


@lru_cache(maxsize=4096)
def _metadata_from_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def _metadata_from_row(row) -> dict[str, Any]:
    if "enriched_metadata_json" not in row.keys():
        return {}
    raw = row["enriched_metadata_json"]
    if not raw:
        return {}
    return _metadata_from_json(str(raw))


def _metadata_list(metadata: dict[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return [
        text
        for item in value
        if (text := str(item).strip()) and len(text) <= 500
    ]


def _row_title_terms(row) -> list[str]:
    metadata_json = (
        row["enriched_metadata_json"]
        if "enriched_metadata_json" in row.keys()
        else None
    )
    extras = []
    if "version_nickname" in row.keys():
        extras.append(row["version_nickname"])
    return game_title_terms(
        title=row["title"],
        original_title=row["original_title"],
        metadata_json=metadata_json,
        extra_terms=extras,
    )


def _game_dict(row, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if metadata is None:
        metadata = _metadata_from_row(row)
    result = {
        "bgg_id": row["bgg_id"],
        "parent_bgg_id": metadata.get("parent_bgg_id"),
        "title": row["title"],
        "original_title": row["original_title"],
        "year_published": row["year_published"],
        "item_type": row["item_type"],
        "players": {"min": row["min_players"], "max": row["max_players"]},
        "play_time": {
            "playing": row["playing_time"],
            "min": row["min_play_time"],
            "max": row["max_play_time"],
        },
        "bgg": {
            "average": row["bgg_average"],
            "bayes_average": row["bgg_bayes_average"],
            "average_weight": row["bgg_average_weight"],
            "rank": row["bgg_rank"],
            "num_owned": row["bgg_num_owned"],
            "best_players": row["bgg_best_players"],
            "recommended_players": row["bgg_recommended_players"],
            "recommended_age": row["bgg_recommended_age"],
            "min_age": row["bgg_recommended_age"],
            "language_dependence": row["bgg_language_dependence"],
            "users_rated": metadata.get("bgg_users_rated"),
        },
        "collection": {
            "coll_id": row["coll_id"],
            "own": bool(row["own"]) if row["own"] is not None else False,
            "for_trade": bool(row["for_trade"]) if row["for_trade"] is not None else False,
            "want": bool(row["want"]) if row["want"] is not None else False,
            "want_to_buy": bool(row["want_to_buy"]) if row["want_to_buy"] is not None else False,
            "want_to_play": bool(row["want_to_play"]) if row["want_to_play"] is not None else False,
            "previously_owned": bool(row["previously_owned"]) if row["previously_owned"] is not None else False,
            "preordered": bool(row["preordered"]) if row["preordered"] is not None else False,
            "wishlist": bool(row["wishlist"]) if row["wishlist"] is not None else False,
            "wishlist_priority": row["wishlist_priority"],
            "rating": row["user_rating"],
            "num_plays": row["num_plays"],
            "barcode": row["barcode"],
            "language": row["version_languages"],
            "publishers": row["version_publishers"],
            "version_year": row["version_year_published"],
            "version_nickname": row["version_nickname"],
            "inventory_location": row["inventory_location"],
            "quantity": row["quantity"],
            "acquisition_date": (
                row["acquisition_date"]
                if "acquisition_date" in row.keys()
                else None
            ),
            "first_seen_at": (
                row["first_seen_at"]
                if "first_seen_at" in row.keys()
                else None
            ),
        },
        "progress": {
            "played": bool(
                ("played_at" in row.keys() and row["played_at"])
                or ("completed_at" in row.keys() and row["completed_at"])
                or int(row["num_plays"] or 0) > 0
            ),
            "played_at": row["played_at"] if "played_at" in row.keys() else None,
            "completed": bool(row["completed_at"]) if "completed_at" in row.keys() else False,
            "completed_at": row["completed_at"] if "completed_at" in row.keys() else None,
            "rating": row["personal_rating"] if "personal_rating" in row.keys() else None,
        },
        "gameplay_summary": (
            row["gameplay_summary"]
            if "gameplay_summary" in row.keys()
            else None
        ),
    }
    if "cover_url" in row.keys():
        result["bgg_metadata"] = {
            "source": row["metadata_source"],
            "cover_url": row["cover_url"],
            "description": row["enriched_description"],
            "fetched_at": row["metadata_fetched_at"],
            "categories": _metadata_list(metadata, "categories"),
            "mechanics": _metadata_list(metadata, "mechanics"),
        }
    return result


_RANGE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–—]\s*(\d{1,2})(?!\d)")
_PLUS_RE = re.compile(r"(?<!\d)(\d{1,2})\s*\+(?!\d)")
_SINGLE_RE = re.compile(r"(?<!\d)(\d{1,2})(?!\d)")


def _player_text_matches(value: str | None, player_count: int) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    for match in _RANGE_RE.finditer(text):
        low, high = int(match.group(1)), int(match.group(2))
        if low <= player_count <= high:
            return True
    for match in _PLUS_RE.finditer(text):
        if player_count >= int(match.group(1)):
            return True
    return any(int(match.group(1)) == player_count for match in _SINGLE_RE.finditer(text))


def language_dependence_level(value: Any) -> int | None:
    """BGG language dependence poll answer as level 1 (none) to 5 (unplayable)."""
    text = str(value or "").strip().casefold()
    for prefix, level in (
        ("no necessary", 1),
        ("some necessary", 2),
        ("moderate", 3),
        ("extensive", 4),
        ("unplayable", 5),
    ):
        if text.startswith(prefix):
            return level
    return None


def _explore_facts(row, title: str) -> dict[str, Any]:
    """Values the Esplora parameters compare, derived once per row."""

    def number(key: str) -> float | None:
        try:
            value = float(row[key]) if row[key] is not None else None
        except (TypeError, ValueError):
            return None
        return value if value and value > 0 else None

    def integer(raw: Any) -> int | None:
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    age_match = re.search(r"\d{1,2}", str(row["bgg_recommended_age"] or ""))
    age = int(age_match.group(0)) if age_match else 0
    minutes = next(
        (
            value
            for key in ("max_play_time", "playing_time", "min_play_time")
            if (value := integer(row[key])) is not None
        ),
        None,
    )
    ideal = {count for count in range(1, 6) if _ideal_players_match(row, count)}
    if any(_ideal_players_match(row, count) for count in range(6, 31)):
        ideal.add(6)
    bayes = number("bgg_bayes_average")
    rating = number("bgg_average")
    return {
        "min_players": integer(row["min_players"]),
        "max_players": integer(row["max_players"]),
        "ideal": ideal,
        "age": age or None,
        "minutes": minutes if minutes and minutes > 0 else None,
        "weight": number("bgg_average_weight"),
        "rating": rating,
        "language": language_dependence_level(row["bgg_language_dependence"]),
        "sort": (
            bayes is None, -(bayes or 0), rating is None, -(rating or 0),
            str(title or "").casefold(), int(row["bgg_id"]),
        ),
    }


def _entry_payload(entry, metadata_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Library game payload, or a catalog card payload shaped like /api/reference items."""
    row = entry[0]
    if entry[5] == "library":
        return {
            **_game_dict(row, metadata=metadata_by_id.get(int(row["bgg_id"]))),
            "source": "library",
        }
    return {
        "source": "catalog",
        "bgg_id": int(row["bgg_id"]),
        "name": row["name"],
        "year_published": row["year_published"],
        "is_expansion": False,
        "rank": row["rank"],
        "average": row["average"],
        "users_rated": row["users_rated"],
        "thumbnail_url": row["thumbnail_url"],
        "image_url": row["image_url"],
        "admission_reason": row["admission_reason"] or "votes",
        "in_catalog": False,
        "owned": False,
        "players": {"min": row["min_players"], "max": row["max_players"]},
        "play_time": {
            "playing": row["playing_time"],
            "min": row["min_play_time"],
            "max": row["max_play_time"],
        },
        "average_weight": row["bgg_average_weight"],
        "recommended_age": row["bgg_recommended_age"],
        "best_players": row["bgg_best_players"],
        "recommended_players": row["bgg_recommended_players"],
        "language_dependence": row["bgg_language_dependence"],
    }



def _ideal_players_match(row, player_count: int) -> bool:
    if row["bgg_best_players"]:
        return _player_text_matches(row["bgg_best_players"], player_count)
    if row["bgg_recommended_players"]:
        return _player_text_matches(row["bgg_recommended_players"], player_count)
    minimum = row["min_players"]
    maximum = row["max_players"]
    return bool(
        minimum is not None
        and maximum is not None
        and int(minimum) <= player_count <= int(maximum)
    )


def _recommended_players_match(row, player_count: int) -> bool:
    if row["bgg_recommended_players"]:
        return _player_text_matches(row["bgg_recommended_players"], player_count)
    minimum = row["min_players"]
    maximum = row["max_players"]
    return bool(
        minimum is not None
        and maximum is not None
        and int(minimum) <= player_count <= int(maximum)
    )


def _ideal_players_label(row) -> str | None:
    raw = str(row["bgg_best_players"] or "").strip()
    if not raw:
        return None
    return raw.replace("-", "–")


def _box_age_label(row) -> str | None:
    raw = str(row["bgg_recommended_age"] or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return f"{raw}+"
    return raw


def _facet_match(row, *, category: str | None, mechanic: str | None) -> bool:
    metadata = _metadata_from_row(row)
    if category:
        wanted = category.casefold()
        if not any(value.casefold() == wanted for value in _metadata_list(metadata, "categories")):
            return False
    if mechanic:
        wanted = mechanic.casefold()
        if not any(value.casefold() == wanted for value in _metadata_list(metadata, "mechanics")):
            return False
    return True


class Catalog:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _from_sql() -> str:
        return """
            FROM board_games g
            LEFT JOIN collection_entries c ON c.board_game_id = g.id
            LEFT JOIN board_game_enrichments e ON e.board_game_id = g.id
            LEFT JOIN game_progress p ON p.board_game_id = g.id
        """

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT g.*, c.coll_id, c.user_rating, c.num_plays, c.own,
                   c.for_trade, c.want, c.want_to_buy, c.want_to_play,
                   c.previously_owned, c.preordered, c.wishlist,
                   c.wishlist_priority, c.barcode, c.version_languages,
                   c.version_publishers, c.version_year_published,
                   c.version_nickname, c.inventory_location, c.quantity,
                   c.acquisition_date, c.first_seen_at,
                   p.played_at, p.completed_at, p.personal_rating,
                   e.source AS metadata_source, e.cover_url,
                   e.description AS enriched_description,
                   e.fetched_at AS metadata_fetched_at,
                   e.metadata_json AS enriched_metadata_json
        """

    def list_games(
        self,
        *,
        query: str | None = None,
        item_type: str | None = None,
        owned: bool | None = None,
        supports_players: int | None = None,
        ideal_players: int | None = None,
        recommended_players: int | None = None,
        player_age: int | None = None,
        weight: str | None = None,
        max_minutes: int | None = None,
        min_rating: float | None = None,
        category: str | None = None,
        mechanic: str | None = None,
        completed: bool | None = None,
        played: bool | None = None,
        personal_rating_min: float | None = None,
        personal_rating_max: float | None = None,
        sort: str = "title",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        search_query = str(query or "").strip()
        if item_type:
            where.append("g.item_type = ?")
            params.append(item_type)
        if owned is not None:
            where.append("COALESCE(c.own, 0) = ?")
            params.append(1 if owned else 0)
        if supports_players is not None:
            where.append(
                "g.min_players IS NOT NULL AND g.max_players IS NOT NULL "
                "AND g.min_players <= ? AND g.max_players >= ?"
            )
            params.extend([supports_players, supports_players])
        if player_age is not None:
            where.append(
                "g.bgg_recommended_age IS NOT NULL "
                "AND CAST(g.bgg_recommended_age AS INTEGER) > 0 "
                "AND CAST(g.bgg_recommended_age AS INTEGER) <= ?"
            )
            params.append(player_age)
        if weight == "light":
            where.append("g.bgg_average_weight IS NOT NULL AND g.bgg_average_weight <= 2.30")
        elif weight == "medium":
            where.append(
                "g.bgg_average_weight IS NOT NULL "
                "AND g.bgg_average_weight > 2.30 AND g.bgg_average_weight <= 3.50"
            )
        elif weight == "heavy":
            where.append("g.bgg_average_weight IS NOT NULL AND g.bgg_average_weight > 3.50")
        if max_minutes is not None:
            where.append(
                "COALESCE(g.max_play_time, g.playing_time, g.min_play_time) IS NOT NULL "
                "AND COALESCE(g.max_play_time, g.playing_time, g.min_play_time) <= ?"
            )
            params.append(max_minutes)
        if min_rating is not None:
            where.append("g.bgg_average IS NOT NULL AND g.bgg_average >= ?")
            params.append(min_rating)
        if completed is not None:
            where.append("p.completed_at IS NOT NULL" if completed else "p.completed_at IS NULL")
        if played is not None:
            played_sql = (
                "(p.played_at IS NOT NULL OR p.completed_at IS NOT NULL "
                "OR COALESCE(c.num_plays,0) > 0)"
            )
            where.append(played_sql if played else f"NOT {played_sql}")
        if personal_rating_min is not None:
            where.append("p.personal_rating IS NOT NULL AND p.personal_rating >= ?")
            params.append(float(personal_rating_min))
        if personal_rating_max is not None:
            where.append("p.personal_rating IS NOT NULL AND p.personal_rating <= ?")
            params.append(float(personal_rating_max))

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_sql = SORT_SQL.get(sort, SORT_SQL["title"])
        from_sql = self._from_sql()
        select_sql = self._select_sql()
        python_filter = (
            bool(search_query)
            or ideal_players is not None
            or recommended_players is not None
            or bool(category)
            or bool(mechanic)
        )

        with self.database.connect() as connection:
            if not python_filter:
                total = connection.execute(
                    f"SELECT COUNT(*) AS count {from_sql} {where_sql}", params
                ).fetchone()["count"]
                rows = connection.execute(
                    f"""
                    {select_sql}
                    {from_sql}
                    {where_sql}
                    ORDER BY {order_sql}
                    LIMIT ? OFFSET ?
                    """,
                    [*params, limit, offset],
                ).fetchall()
            else:
                candidates = connection.execute(
                    f"""
                    {select_sql}
                    {from_sql}
                    {where_sql}
                    ORDER BY {order_sql}
                    """,
                    params,
                ).fetchall()
                filtered = [
                    row
                    for row in candidates
                    if (
                        not search_query
                        or title_query_matches(search_query, _row_title_terms(row))
                    )
                    and (
                        ideal_players is None
                        or _ideal_players_match(row, ideal_players)
                    )
                    and (
                        recommended_players is None
                        or _recommended_players_match(row, recommended_players)
                    )
                    and _facet_match(row, category=category, mechanic=mechanic)
                ]
                total = len(filtered)
                rows = filtered[offset : offset + limit]

        return {
            "items": [_game_dict(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "sort": sort if sort in SORT_SQL else "title",
        }

    def get_game(self, bgg_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                f"""
                {self._select_sql()}
                {self._from_sql()}
                WHERE g.bgg_id = ?
                ORDER BY c.id
                LIMIT 1
                """,
                (bgg_id,),
            ).fetchone()
        return _game_dict(row) if row else None

    def refreshable_metadata_ids(self, *, limit: int = 20) -> list[int]:
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id
                FROM board_games g
                LEFT JOIN board_game_enrichments e ON e.board_game_id = g.id
                WHERE e.board_game_id IS NULL
                   OR e.next_refresh_at IS NULL
                   OR e.next_refresh_at <= ?
                   OR e.metadata_json NOT LIKE '%"parent_bgg_id"%'
                   OR e.metadata_json NOT LIKE '%"mechanics"%'
                   OR e.metadata_json NOT LIKE '%"alternate_titles"%'
                   OR e.metadata_json NOT LIKE '%"player_poll"%'
                ORDER BY
                    e.board_game_id IS NOT NULL,
                    g.title COLLATE NOCASE,
                    g.bgg_id
                LIMIT ?
                """,
                (now, max(1, min(int(limit), 20))),
            ).fetchall()
        return [int(row["bgg_id"]) for row in rows]

    def missing_metadata_ids(self, *, limit: int = 20) -> list[int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id
                FROM board_games g
                LEFT JOIN board_game_enrichments e ON e.board_game_id = g.id
                WHERE e.board_game_id IS NULL
                ORDER BY g.title COLLATE NOCASE, g.bgg_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [int(row["bgg_id"]) for row in rows]

    def all_metadata_ids(self, *, limit: int = 250, offset: int = 0) -> list[int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT bgg_id FROM board_games
                   ORDER BY title COLLATE NOCASE,bgg_id LIMIT ? OFFSET ?""",
                (max(1, min(int(limit), 250)), max(0, int(offset))),
            ).fetchall()
        return [int(row["bgg_id"]) for row in rows]

    def missing_metadata_count(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM board_games g
                LEFT JOIN board_game_enrichments e ON e.board_game_id = g.id
                WHERE e.board_game_id IS NULL
                """
            ).fetchone()
        return int(row["count"] or 0)

    def _discovery_entries(
        self, source: str, reference_rows: list[dict[str, Any]] | None
    ) -> tuple[list[tuple[Any, ...]], dict[int, dict[str, Any]]]:
        """Owned base games and/or visible catalog titles not owned, for Esplora and Classifiche.

        Each entry is (row, categories, mechanics, category groups, mechanic
        groups, origin, facts); rows of both origins share library column names.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._select_sql()}
                {self._from_sql()}
                WHERE COALESCE(c.own,0)=1
                  AND COALESCE(g.item_type,'standalone') != 'expansion'
                ORDER BY g.title COLLATE NOCASE, g.bgg_id
                """
            ).fetchall()

        # Multiple physical copies must not inflate either result or facet counts.
        library: dict[int, Any] = {}
        for row in rows:
            library.setdefault(int(row["bgg_id"]), row)

        # entry: (row, categories, mechanics, category groups, mechanic groups, origin, facts)
        entries: list[tuple[Any, ...]] = []

        def derive(row, category_list, mechanic_list, title) -> tuple[Any, ...]:
            category_names = {value.casefold(): value for value in category_list}
            mechanic_names = {value.casefold(): value for value in mechanic_list}
            return (
                category_names,
                mechanic_names,
                {group_key("category", name) for name in category_names.values()},
                {group_key("mechanic", name) for name in mechanic_names.values()},
                _explore_facts(row, title),
            )

        def add_entry(row, derived: tuple[Any, ...], origin: str) -> None:
            entries.append((row, *derived[:4], origin, derived[4]))

        metadata_by_id: dict[int, dict[str, Any]] = {}
        if source in {"library", "both"}:
            for bgg_id, row in library.items():
                metadata = _metadata_from_row(row)
                metadata_by_id[bgg_id] = metadata
                if not row["bgg_language_dependence"] and metadata.get("bgg_language_dependence"):
                    row = {**dict(row), "bgg_language_dependence": metadata["bgg_language_dependence"]}
                add_entry(
                    row,
                    derive(
                        row,
                        _metadata_list(metadata, "categories"),
                        _metadata_list(metadata, "mechanics"),
                        row["title"],
                    ),
                    "library",
                )
        if source in {"catalog", "both"}:
            if reference_rows is None:
                from boardgamecompanion.bgg_reference import BggReferenceCatalog

                reference_rows = BggReferenceCatalog(self.database).explore_rows()
            for row in reference_rows:
                if int(row["bgg_id"]) in library:
                    continue
                # Derived values live on the cached scan row, computed once per scan.
                derived = row.get("_explore")
                if derived is None:
                    derived = derive(row, row["categories"], row["mechanics"], row["name"])
                    row["_explore"] = derived
                add_entry(row, derived, "catalog")

        return entries, metadata_by_id

    def explore(
        self,
        *,
        source: str = "library",
        categories: list[str] | None = None,
        mechanics: list[str] | None = None,
        category_groups: list[str] | None = None,
        mechanic_groups: list[str] | None = None,
        supports_players: int | None = None,
        ideal_players: int | None = None,
        player_age: int | None = None,
        weight: str | None = None,
        max_minutes: int | None = None,
        min_rating: float | None = None,
        max_language: int | None = None,
        limit: int = 250,
        reference_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Intersect owned games and/or BGG catalog titles on facets and parameters.

        ``source`` is ``library`` (owned base games), ``catalog`` (visible BGG
        reference titles not owned) or ``both``. Selected macro groups match
        a game having any member of the group; everything else is ANDed.
        """
        source = source if source in {"library", "catalog", "both"} else "library"

        def clean(values: list[str] | None) -> list[str]:
            return list(dict.fromkeys(
                text for value in (values or []) if (text := str(value).strip())
            ))

        selected_categories = clean(categories)
        selected_mechanics = clean(mechanics)
        selected_category_groups = [
            key for key in clean(category_groups) if key in valid_group_keys("category")
        ]
        selected_mechanic_groups = [
            key for key in clean(mechanic_groups) if key in valid_group_keys("mechanic")
        ]
        wanted_categories = {value.casefold() for value in selected_categories}
        wanted_mechanics = {value.casefold() for value in selected_mechanics}

        entries, metadata_by_id = self._discovery_entries(source, reference_rows)

        faceted = [
            entry
            for entry in entries
            if wanted_categories.issubset(entry[1])
            and wanted_mechanics.issubset(entry[2])
            and all(key in entry[3] for key in selected_category_groups)
            and all(key in entry[4] for key in selected_mechanic_groups)
        ]

        def optional_match(facts: dict[str, Any], key: str, value: Any) -> bool:
            if key == "supports_players":
                count = int(value)
                minimum, maximum = facts["min_players"], facts["max_players"]
                if minimum is None or maximum is None:
                    return False
                return maximum >= 6 if count >= 6 else minimum <= count <= maximum
            if key == "ideal_players":
                return min(int(value), 6) in facts["ideal"]
            if key == "player_age":
                return facts["age"] is not None and facts["age"] <= int(value)
            if key == "weight":
                numeric = facts["weight"]
                if numeric is None:
                    return False
                if value == "light":
                    return numeric <= 2.30
                if value == "medium":
                    return 2.30 < numeric <= 3.50
                if value == "heavy":
                    return numeric > 3.50
                return True
            if key == "max_minutes":
                return facts["minutes"] is not None and facts["minutes"] <= int(value)
            if key == "min_rating":
                return facts["rating"] is not None and facts["rating"] >= float(value)
            if key == "max_language":
                return facts["language"] is not None and facts["language"] <= int(value)
            return True

        active_optional: dict[str, Any] = {
            "supports_players": supports_players,
            "ideal_players": ideal_players,
            "player_age": player_age,
            "weight": weight,
            "max_minutes": max_minutes,
            "min_rating": min_rating,
            "max_language": max_language,
        }

        active_items = [
            (key, value) for key, value in active_optional.items()
            if value is not None and value != ""
        ]

        def matches_optional(facts: dict[str, Any], *, skip: str | None = None) -> bool:
            return all(
                optional_match(facts, key, value)
                for key, value in active_items
                if key != skip
            )

        matched = sorted(
            (entry for entry in faceted if matches_optional(entry[6])),
            key=lambda entry: entry[6]["sort"],
        )

        def build_facets(kind: str, key_index: int, selected: list[str]) -> list[dict[str, Any]]:
            counts: Counter[str] = Counter()
            display_names: dict[str, str] = {}
            covers: dict[str, list[str]] = {}
            for entry in matched:
                cover = str(entry[0]["cover_url"] or "").strip()
                for folded, display in entry[key_index].items():
                    counts[folded] += 1
                    display_names.setdefault(folded, display)
                    bucket = covers.setdefault(folded, [])
                    if cover and cover not in bucket and len(bucket) < 4:
                        bucket.append(cover)

            selected_map = {value.casefold(): value for value in selected}
            items: list[dict[str, Any]] = []
            for folded in set(counts) | set(selected_map):
                name = display_names.get(folded, selected_map.get(folded, folded))
                items.append(
                    {
                        "name": name,
                        "group": group_key(kind, name),
                        "count": int(counts.get(folded, 0)),
                        "covers": covers.get(folded, []),
                        "selected": folded in selected_map,
                    }
                )
            items.sort(
                key=lambda item: (
                    not bool(item["selected"]),
                    -int(item["count"]),
                    str(item["name"]).casefold(),
                )
            )
            return items

        def build_groups(kind: str, key_index: int, selected: list[str]) -> list[dict[str, Any]]:
            counts: Counter[str] = Counter()
            for entry in matched:
                counts.update(entry[key_index])
            return [
                {
                    **group,
                    "count": int(counts.get(group["key"], 0)),
                    "selected": group["key"] in selected,
                }
                for group in group_definitions(kind)
            ]

        option_specs: dict[str, list[tuple[Any, str]]] = {
            "supports_players": [
                (1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6+"),
            ],
            "ideal_players": [
                (1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6+"),
            ],
            "player_age": [
                (6, "6"), (8, "8"), (10, "10"), (12, "12"),
                (14, "14"), (16, "16+"),
            ],
            "max_minutes": [
                (30, "≤30"), (45, "≤45"), (60, "≤60"),
                (90, "≤90"), (120, "≤120"), (180, "≤180"),
            ],
            "weight": [
                ("light", "Semplice"),
                ("medium", "Media"),
                ("heavy", "Impegnativa"),
            ],
            "min_rating": [
                (6.0, "6+"), (6.5, "6,5+"), (7.0, "7+"),
                (7.5, "7,5+"), (8.0, "8+"), (8.5, "8,5+"),
            ],
            "max_language": [
                (1, "Nessuna"),
                (2, "Poca"),
                (3, "Moderata"),
            ],
        }

        def contextual_options(key: str) -> list[dict[str, Any]]:
            # Self-excluding facet calculation: other active filters stay in
            # force, while this group is temporarily removed so valid
            # alternatives remain visible.
            source_rows = [entry[6] for entry in faceted if matches_optional(entry[6], skip=key)]
            current = active_optional[key]
            items: list[dict[str, Any]] = []
            for value, label in option_specs[key]:
                count = sum(1 for row in source_rows if optional_match(row, key, value))
                selected = (
                    str(current) == str(value)
                    if current is not None and current != ""
                    else False
                )
                if count <= 0 and not selected:
                    continue
                items.append(
                    {
                        "value": value,
                        "label": label,
                        "count": count,
                        "selected": selected,
                    }
                )
            return items

        capped = max(1, min(int(limit), 250))
        return {
            "source": source,
            "total": len(matched),
            "category_groups": build_groups("category", 3, selected_category_groups),
            "mechanic_groups": build_groups("mechanic", 4, selected_mechanic_groups),
            "categories": build_facets("category", 1, selected_categories),
            "mechanics": build_facets("mechanic", 2, selected_mechanics),
            "games": [_entry_payload(entry, metadata_by_id) for entry in matched[:capped]],
            "limit": capped,
            "filters": {
                "categories": selected_categories,
                "mechanics": selected_mechanics,
                "category_groups": selected_category_groups,
                "mechanic_groups": selected_mechanic_groups,
                **active_optional,
            },
            "options": {
                key: contextual_options(key)
                for key in option_specs
            },
        }

    def facets(self, *, owned_only: bool = True, limit: int = 40) -> dict[str, Any]:
        where = "WHERE COALESCE(c.own,0)=1" if owned_only else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT g.item_type,e.metadata_json AS enriched_metadata_json
                {self._from_sql()}
                {where}
                """
            ).fetchall()
        categories: Counter[str] = Counter()
        mechanics: Counter[str] = Counter()
        for row in rows:
            metadata = _metadata_from_row(row)
            for value in set(_metadata_list(metadata, "categories")):
                categories[value] += 1
            for value in set(_metadata_list(metadata, "mechanics")):
                mechanics[value] += 1
        cap = max(1, min(int(limit), 100))
        return {
            "categories": [
                {"name": name, "count": count}
                for name, count in categories.most_common(cap)
            ],
            "mechanics": [
                {"name": name, "count": count}
                for name, count in mechanics.most_common(cap)
            ],
        }

    def rankings(
        self,
        *,
        mode: str = "overall",
        source: str = "library",
        category: str | None = None,
        mechanic: str | None = None,
        category_groups: list[str] | None = None,
        mechanic_groups: list[str] | None = None,
        ideal_players: int | None = None,
        max_minutes: int | None = None,
        weight: str | None = None,
        max_language: int | None = None,
        limit: int = 50,
        reference_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Score owned games and/or catalog titles with one of the ranking algorithms.

        Filters are ANDed; option and group counts exclude their own filter so
        alternatives stay visible, as in Esplora.
        """
        modes = {
            "overall": {
                "title": "Migliori in assoluto",
                "description": "Giochi ordinati per voto medio BGG.",
            },
            "outside_top": {
                "title": "Fuori dalla Top 500",
                "description": "Giochi con voto medio solido oltre la posizione 500 BGG.",
            },
            "quality_time": {
                "title": "Qualità / tempo",
                "description": "Premia giochi solidi che offrono molto in una durata contenuta.",
            },
            "gateway": {
                "title": "Gateway",
                "description": "Qualità, accessibilità, durata ragionevole e versatilità al tavolo.",
            },
            "expert": {
                "title": "Per esperti",
                "description": "Titoli di qualità con maggiore profondità e complessità.",
            },
            "safe_choice": {
                "title": "Scelta sicura",
                "description": "Giochi affidabili, versatili e poco rischiosi quando non sai cosa scegliere.",
            },
            "personal_favorites": {
                "title": "Preferiti personali",
                "description": "Il tuo voto personale domina, con BGG come tie-break ragionato.",
            },
        }
        selected_mode = mode if mode in modes else "overall"
        source = source if source in {"library", "catalog", "both"} else "library"
        selected_category_groups = [
            key for key in dict.fromkeys(category_groups or []) if key in valid_group_keys("category")
        ]
        selected_mechanic_groups = [
            key for key in dict.fromkeys(mechanic_groups or []) if key in valid_group_keys("mechanic")
        ]
        entries, metadata_by_id = self._discovery_entries(source, reference_rows)

        def minutes(row) -> int | None:
            raw = row["playing_time"]
            if raw is None:
                raw = row["max_play_time"]
            if raw is None:
                raw = row["min_play_time"]
            try:
                value = int(raw) if raw is not None else 0
            except (TypeError, ValueError):
                return None
            return value if value > 0 else None

        def quality(row) -> float:
            raw = row["bgg_average"]
            if raw is None:
                return 0.0
            return max(0.0, min(100.0, float(raw) * 10.0))

        def broad_player_score(row) -> float:
            minimum = row["min_players"]
            maximum = row["max_players"]
            if minimum is None or maximum is None:
                return 35.0
            span = max(0, int(maximum) - int(minimum))
            return max(25.0, min(100.0, 45.0 + span * 14.0))

        def duration_score(row, *, target: int = 75) -> float:
            value = minutes(row)
            if value is None:
                return 45.0
            delta = abs(value - target)
            return max(20.0, 100.0 - min(80.0, delta * 0.75))

        def accessibility_score(row) -> float:
            raw_weight = row["bgg_average_weight"]
            weight_value = float(raw_weight) if raw_weight is not None else 2.5
            weight_score = max(20.0, 100.0 - abs(weight_value - 2.0) * 34.0)
            duration = duration_score(row, target=60)
            player = broad_player_score(row)
            return weight_score * 0.45 + duration * 0.35 + player * 0.20

        def expert_score(row) -> float:
            raw_weight = row["bgg_average_weight"]
            if raw_weight is None:
                return 35.0
            value = float(raw_weight)
            return max(20.0, min(100.0, 25.0 + (value - 2.0) * 30.0))

        def calculate(row, origin: str) -> tuple[float, str, list[str]] | None:
            # Catalog titles without a BGG rank have too little rating history
            # to compete in these rating-based lists.
            if origin == "catalog" and int(row["bgg_rank"] or 0) <= 0:
                return None
            q = quality(row)
            user_rating = (
                float(row["user_rating"])
                if origin == "library" and row["user_rating"] is not None
                else None
            )
            raw_weight = row["bgg_average_weight"]
            weight_value = float(raw_weight) if raw_weight is not None else None
            duration = minutes(row)
            rank = int(row["bgg_rank"] or 0)
            factors: list[str] = []

            if selected_mode == "overall":
                if q <= 0:
                    return None
                score = q
                reason = "rating BGG"

            elif selected_mode == "outside_top":
                if q < 60 or rank <= 500:
                    return None
                score = q
                factors.append(f"BGG #{rank}")
                reason = "qualità solida pur essendo fuori dalla Top 500 BGG"

            elif selected_mode == "quality_time":
                if q <= 0 or duration is None:
                    return None
                efficiency = 100.0 / (1.0 + max(0, duration - 30) / 120.0)
                score = q * 0.82 + efficiency * 0.18
                factors.append(f"efficienza {efficiency:.0f}")
                reason = "molta qualità per il tempo richiesto"

            elif selected_mode == "gateway":
                if q <= 0:
                    return None
                access = accessibility_score(row)
                score = q * 0.67 + access * 0.33
                factors.append(f"accessibilità {access:.0f}")
                reason = "buon equilibrio tra qualità, semplicità, durata e versatilità"

            elif selected_mode == "expert":
                if q <= 0:
                    return None
                depth = expert_score(row)
                if depth < 45:
                    return None
                score = q * 0.76 + depth * 0.24
                factors.append(f"profondità {depth:.0f}")
                reason = "qualità elevata con complessità adatta a giocatori esperti"

            elif selected_mode == "safe_choice":
                if q <= 0:
                    return None
                versatility = (
                    broad_player_score(row) * 0.55
                    + duration_score(row, target=75) * 0.25
                    + accessibility_score(row) * 0.20
                )
                score = q * 0.70 + versatility * 0.30
                factors.append(f"versatilità {versatility:.0f}")
                reason = "qualità solida e buona adattabilità a tavoli diversi"

            elif selected_mode == "personal_favorites":
                if user_rating is None or user_rating <= 0:
                    return None
                personal = max(0.0, min(100.0, user_rating * 10.0))
                score = personal * 0.84 + q * 0.16
                factors.append(f"tuo voto {user_rating:.1f}")
                reason = "il tuo voto personale domina la posizione"

            else:
                return None

            ideal_label = _ideal_players_label(row)
            if ideal_label:
                factors.insert(0, f"ideale in {ideal_label}")
            if weight_value is not None:
                factors.append(f"peso {weight_value:.1f}")
            age_label = _box_age_label(row)
            if age_label:
                factors.append(f"età {age_label}")
            return max(0.0, min(100.0, score)), reason, factors[:4]

        scored: list[tuple[tuple[Any, ...], tuple[float, str, list[str]]]] = []
        for entry in entries:
            calculated = calculate(entry[0], entry[5])
            if calculated is not None:
                scored.append((entry, calculated))

        def weight_match(entry, value: str) -> bool:
            numeric = entry[6]["weight"]
            if numeric is None:
                return False
            if value == "light":
                return numeric <= 2.30
            if value == "medium":
                return 2.30 < numeric <= 3.50
            return numeric > 3.50

        wanted_category = str(category or "").strip().casefold()
        wanted_mechanic = str(mechanic or "").strip().casefold()
        predicates: dict[str, tuple[Any, Any]] = {
            "category": (wanted_category, lambda e, v: v in e[1]),
            "mechanic": (wanted_mechanic, lambda e, v: v in e[2]),
            "category_groups": (selected_category_groups, lambda e, v: all(k in e[3] for k in v)),
            "mechanic_groups": (selected_mechanic_groups, lambda e, v: all(k in e[4] for k in v)),
            "ideal_players": (ideal_players, lambda e, v: min(int(v), 6) in e[6]["ideal"]),
            "max_minutes": (
                max_minutes,
                lambda e, v: (m := minutes(e[0])) is not None and m <= int(v),
            ),
            "weight": (weight, weight_match),
            "max_language": (
                max_language,
                lambda e, v: e[6]["language"] is not None and e[6]["language"] <= int(v),
            ),
        }
        active = [
            (key, value, check)
            for key, (value, check) in predicates.items()
            if value not in (None, "", [])
        ]

        def passes(entry, *, skip: tuple[str, ...] = ()) -> bool:
            return all(check(entry, value) for key, value, check in active if key not in skip)

        option_specs: dict[str, list[tuple[Any, str]]] = {
            "ideal_players": [(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6+")],
            "max_minutes": [(30, "≤30"), (60, "≤60"), (90, "≤90"), (120, "≤120"), (180, "≤180")],
            "weight": [("light", "Semplice"), ("medium", "Media"), ("heavy", "Impegnativa")],
            "max_language": [(1, "Nessuna"), (2, "Poca"), (3, "Moderata")],
        }

        def options(key: str) -> list[dict[str, Any]]:
            pool = [entry for entry, _ in scored if passes(entry, skip=(key,))]
            current = predicates[key][0]
            check = predicates[key][1]
            items = []
            for value, label in option_specs[key]:
                count = sum(1 for entry in pool if check(entry, value))
                selected = current not in (None, "") and str(current) == str(value)
                if count or selected:
                    items.append({"value": value, "label": label, "count": count, "selected": selected})
            return items

        def groups(kind: str, index: int, selected: list[str]) -> list[dict[str, Any]]:
            pool = [
                entry for entry, _ in scored
                if passes(entry, skip=(f"{kind}_groups", kind))
            ]
            counts: Counter[str] = Counter()
            for entry in pool:
                counts.update(entry[index])
            return [
                {**group, "count": int(counts.get(group["key"], 0)), "selected": group["key"] in selected}
                for group in group_definitions(kind)
            ]

        def facets(kind: str, index: int, wanted: str) -> list[dict[str, Any]]:
            pool = [entry for entry, _ in scored if passes(entry, skip=(kind,))]
            counts: Counter[str] = Counter()
            names: dict[str, str] = {}
            for entry in pool:
                for folded, name in entry[index].items():
                    counts[folded] += 1
                    names.setdefault(folded, name)
            items = [
                {
                    "name": names[folded],
                    "group": group_key(kind, names[folded]),
                    "count": count,
                    "selected": folded == wanted,
                }
                for folded, count in counts.items()
            ]
            items.sort(key=lambda item: (-item["count"], item["name"].casefold()))
            return items

        ranked = [(entry, calc) for entry, calc in scored if passes(entry)]
        ranked.sort(
            key=lambda pair: (
                -round(pair[1][0], 1),
                str(pair[0][0]["title"] if pair[0][5] == "library" else pair[0][0]["name"]).casefold(),
                int(pair[0][0]["bgg_id"]),
            )
        )
        cap = max(1, min(int(limit), 100))
        return {
            "mode": selected_mode,
            "source": source,
            "title": modes[selected_mode]["title"],
            "description": modes[selected_mode]["description"],
            "items": [
                {
                    "game": _entry_payload(entry, metadata_by_id),
                    "score": round(score, 1),
                    "reason": reason,
                    "factors": factors,
                }
                for entry, (score, reason, factors) in ranked[:cap]
            ],
            "total": len(ranked),
            "category_groups": groups("category", 3, selected_category_groups),
            "mechanic_groups": groups("mechanic", 4, selected_mechanic_groups),
            "categories": facets("category", 1, wanted_category),
            "mechanics": facets("mechanic", 2, wanted_mechanic),
            "options": {key: options(key) for key in option_specs},
            "filters": {
                "category": category,
                "mechanic": mechanic,
                "category_groups": selected_category_groups,
                "mechanic_groups": selected_mechanic_groups,
                "ideal_players": ideal_players,
                "max_minutes": max_minutes,
                "weight": weight,
                "max_language": max_language,
            },
        }

    def assistant_candidates(self, *, limit: int = 220) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._select_sql()}
                {self._from_sql()}
                WHERE COALESCE(c.own,0)=1
                  AND COALESCE(g.item_type,'standalone') != 'expansion'
                ORDER BY g.bgg_average IS NULL,g.bgg_average DESC,g.title COLLATE NOCASE
                LIMIT ?
                """,
                (max(1, min(int(limit), 250)),),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            game = _game_dict(row)
            result.append(
                {
                    "bgg_id": game["bgg_id"],
                    "title": game["title"],
                    "owned": True,
                    "players": game["players"],
                    "recommended_players": game["bgg"]["recommended_players"],
                    "best_players": game["bgg"]["best_players"],
                    "min_age": game["bgg"]["recommended_age"],
                    "minutes": game["play_time"],
                    "weight": game["bgg"]["average_weight"],
                    "rating": game["bgg"]["average"],
                    "rank": game["bgg"]["rank"],
                    "categories": game.get("bgg_metadata", {}).get("categories", []),
                    "mechanics": game.get("bgg_metadata", {}).get("mechanics", []),
                }
            )
        return result

    def stats(self) -> dict[str, int]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN item_type = 'standalone' THEN 1 ELSE 0 END) AS standalone,
                    SUM(CASE WHEN item_type = 'expansion' THEN 1 ELSE 0 END) AS expansions
                FROM board_games
                """
            ).fetchone()
            owned = connection.execute(
                "SELECT COUNT(*) AS count FROM collection_entries WHERE own = 1"
            ).fetchone()["count"]
            owned_types = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN COALESCE(g.item_type,'standalone') != 'expansion' THEN 1 ELSE 0 END)
                        AS standalone_owned,
                    SUM(CASE WHEN g.item_type = 'expansion' THEN 1 ELSE 0 END)
                        AS expansions_owned
                FROM collection_entries c
                JOIN board_games g ON g.id = c.board_game_id
                WHERE c.own = 1
                """
            ).fetchone()
            completed = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM game_progress p
                JOIN board_games g ON g.id = p.board_game_id
                WHERE p.completed_at IS NOT NULL
                  AND COALESCE(g.item_type,'standalone') != 'expansion'
                """
            ).fetchone()["count"]
            played = connection.execute(
                """
                SELECT COUNT(DISTINCT g.id) AS count
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                LEFT JOIN game_progress p ON p.board_game_id=g.id
                WHERE COALESCE(g.item_type,'standalone') != 'expansion'
                  AND (
                    p.played_at IS NOT NULL
                    OR p.completed_at IS NOT NULL
                    OR COALESCE(c.num_plays,0) > 0
                  )
                """
            ).fetchone()["count"]
            rulebooks = connection.execute(
                """
                SELECT COUNT(DISTINCT board_game_id) AS count
                FROM game_documents
                WHERE document_type='rulebook'
                """
            ).fetchone()["count"]
        return {
            "total": row["total"] or 0,
            "standalone": row["standalone"] or 0,
            "expansions": row["expansions"] or 0,
            "owned": owned or 0,
            "standalone_owned": owned_types["standalone_owned"] or 0,
            "expansions_owned": owned_types["expansions_owned"] or 0,
            "completed": completed or 0,
            "played": played or 0,
            "rulebooks": rulebooks or 0,
        }

