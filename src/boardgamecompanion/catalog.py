from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from boardgamecompanion.database import Database


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
}


def _metadata_from_row(row) -> dict[str, Any]:
    if "enriched_metadata_json" not in row.keys():
        return {}
    raw = row["enriched_metadata_json"]
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def _metadata_list(metadata: dict[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return [
        text
        for item in value
        if (text := str(item).strip()) and len(text) <= 500
    ]


def _game_dict(row) -> dict[str, Any]:
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
            "language_dependence": row["bgg_language_dependence"],
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
        },
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
        player_age: int | None = None,
        weight: str | None = None,
        max_minutes: int | None = None,
        min_rating: float | None = None,
        category: str | None = None,
        mechanic: str | None = None,
        sort: str = "title",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if query:
            where.append("(g.title LIKE ? COLLATE NOCASE OR g.original_title LIKE ? COLLATE NOCASE)")
            wildcard = f"%{query}%"
            params.extend([wildcard, wildcard])
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

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_sql = SORT_SQL.get(sort, SORT_SQL["title"])
        from_sql = self._from_sql()
        select_sql = self._select_sql()
        python_filter = ideal_players is not None or bool(category) or bool(mechanic)

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
                        ideal_players is None
                        or _ideal_players_match(row, ideal_players)
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

    def explore(
        self,
        *,
        categories: list[str] | None = None,
        mechanics: list[str] | None = None,
        supports_players: int | None = None,
        ideal_players: int | None = None,
        player_age: int | None = None,
        weight: str | None = None,
        max_minutes: int | None = None,
        min_rating: float | None = None,
        limit: int = 250,
    ) -> dict[str, Any]:
        selected_categories = [
            str(value).strip()
            for value in (categories or [])
            if str(value).strip()
        ]
        selected_mechanics = [
            str(value).strip()
            for value in (mechanics or [])
            if str(value).strip()
        ]
        wanted_categories = {value.casefold() for value in selected_categories}
        wanted_mechanics = {value.casefold() for value in selected_mechanics}

        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._select_sql()}
                {self._from_sql()}
                WHERE COALESCE(c.own,0)=1
                  AND COALESCE(g.item_type,'standalone') != 'expansion'
                ORDER BY
                    g.bgg_average IS NULL,
                    g.bgg_average DESC,
                    g.title COLLATE NOCASE,
                    g.bgg_id
                """
            ).fetchall()

        # Multiple physical copies must not inflate either result or facet counts.
        by_bgg_id: dict[int, Any] = {}
        for row in rows:
            by_bgg_id.setdefault(int(row["bgg_id"]), row)
        candidates = list(by_bgg_id.values())

        def row_facets(row, key: str) -> tuple[set[str], dict[str, str]]:
            metadata = _metadata_from_row(row)
            values = _metadata_list(metadata, key)
            canonical = {value.casefold(): value for value in values}
            return set(canonical), canonical

        row_metadata: dict[int, tuple[dict[str, str], dict[str, str]]] = {}
        faceted: list[Any] = []
        for row in candidates:
            category_keys, category_names = row_facets(row, "categories")
            mechanic_keys, mechanic_names = row_facets(row, "mechanics")
            if not wanted_categories.issubset(category_keys):
                continue
            if not wanted_mechanics.issubset(mechanic_keys):
                continue
            faceted.append(row)
            row_metadata[int(row["bgg_id"])] = (category_names, mechanic_names)

        def recommended_age(row) -> int | None:
            raw = str(row["bgg_recommended_age"] or "").strip()
            match = re.search(r"\d{1,2}", raw)
            value = int(match.group(0)) if match else 0
            return value if value > 0 else None

        def play_minutes(row) -> int | None:
            raw = row["max_play_time"]
            if raw is None:
                raw = row["playing_time"]
            if raw is None:
                raw = row["min_play_time"]
            try:
                value = int(raw) if raw is not None else 0
            except (TypeError, ValueError):
                return None
            return value if value > 0 else None

        def supports_count(row, player_count: int) -> bool:
            minimum = row["min_players"]
            maximum = row["max_players"]
            if minimum is None or maximum is None:
                return False
            if player_count >= 6:
                return int(maximum) >= 6
            return int(minimum) <= player_count <= int(maximum)

        def ideal_count(row, player_count: int) -> bool:
            if player_count >= 6:
                return any(_ideal_players_match(row, value) for value in range(6, 31))
            return _ideal_players_match(row, player_count)

        def optional_match(row, key: str, value: Any) -> bool:
            if key == "supports_players":
                return supports_count(row, int(value))
            if key == "ideal_players":
                return ideal_count(row, int(value))
            if key == "player_age":
                age = recommended_age(row)
                return age is not None and age <= int(value)
            if key == "weight":
                raw = row["bgg_average_weight"]
                if raw is None:
                    return False
                numeric = float(raw)
                if value == "light":
                    return numeric <= 2.30
                if value == "medium":
                    return 2.30 < numeric <= 3.50
                if value == "heavy":
                    return numeric > 3.50
                return True
            if key == "max_minutes":
                minutes = play_minutes(row)
                return minutes is not None and minutes <= int(value)
            if key == "min_rating":
                raw = row["bgg_average"]
                return raw is not None and float(raw) >= float(value)
            return True

        active_optional: dict[str, Any] = {
            "supports_players": supports_players,
            "ideal_players": ideal_players,
            "player_age": player_age,
            "weight": weight,
            "max_minutes": max_minutes,
            "min_rating": min_rating,
        }

        def matches_optional(row, *, skip: str | None = None) -> bool:
            for key, value in active_optional.items():
                if key == skip or value is None or value == "":
                    continue
                if not optional_match(row, key, value):
                    return False
            return True

        matched = [row for row in faceted if matches_optional(row)]

        def build_facets(
            key_index: int,
            selected: list[str],
        ) -> list[dict[str, Any]]:
            counts: Counter[str] = Counter()
            display_names: dict[str, str] = {}
            covers: dict[str, list[str]] = {}
            for row in matched:
                names = row_metadata[int(row["bgg_id"])][key_index]
                cover = str(row["cover_url"] or "").strip()
                for folded, display in names.items():
                    counts[folded] += 1
                    display_names.setdefault(folded, display)
                    if cover:
                        bucket = covers.setdefault(folded, [])
                        if cover not in bucket and len(bucket) < 4:
                            bucket.append(cover)

            selected_map = {value.casefold(): value for value in selected}
            all_keys = set(counts) | set(selected_map)
            items: list[dict[str, Any]] = []
            for folded in all_keys:
                name = display_names.get(folded, selected_map.get(folded, folded))
                items.append(
                    {
                        "name": name,
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
        }

        def contextual_options(key: str) -> list[dict[str, Any]]:
            # Self-excluding facet calculation: other active filters stay in
            # force, while this group is temporarily removed so valid
            # alternatives remain visible.
            source = [row for row in faceted if matches_optional(row, skip=key)]
            current = active_optional[key]
            items: list[dict[str, Any]] = []
            for value, label in option_specs[key]:
                count = sum(1 for row in source if optional_match(row, key, value))
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
            "total": len(matched),
            "categories": build_facets(0, selected_categories),
            "mechanics": build_facets(1, selected_mechanics),
            "games": [_game_dict(row) for row in matched[:capped]],
            "limit": capped,
            "filters": {
                "categories": selected_categories,
                "mechanics": selected_mechanics,
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
        return {
            "total": row["total"] or 0,
            "standalone": row["standalone"] or 0,
            "expansions": row["expansions"] or 0,
            "owned": owned or 0,
        }
