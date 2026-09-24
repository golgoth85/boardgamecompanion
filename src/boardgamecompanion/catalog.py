from __future__ import annotations

from typing import Any

from boardgamecompanion.database import Database
from boardgamecompanion.metadata import (
    METADATA_CATALOG_SELECT,
    PROVIDER as METADATA_PROVIDER,
    metadata_from_catalog_row,
)


SORT_SQL = {
    "title": "g.title COLLATE NOCASE ASC, g.bgg_id ASC",
    "year_desc": "g.year_published IS NULL, g.year_published DESC, g.title COLLATE NOCASE ASC",
    "rating_desc": "g.bgg_average IS NULL, g.bgg_average DESC, g.title COLLATE NOCASE ASC",
    "rank_asc": "g.bgg_rank IS NULL OR g.bgg_rank = 0, g.bgg_rank ASC, g.title COLLATE NOCASE ASC",
    "weight_desc": "g.bgg_average_weight IS NULL, g.bgg_average_weight DESC, g.title COLLATE NOCASE ASC",
}


def _game_dict(row) -> dict[str, Any]:
    return {
        "bgg_id": row["bgg_id"],
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
        "metadata": metadata_from_catalog_row(row),
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


class Catalog:
    def __init__(self, database: Database):
        self.database = database

    def list_games(
        self,
        *,
        query: str | None = None,
        item_type: str | None = None,
        owned: bool | None = None,
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

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_sql = SORT_SQL.get(sort, SORT_SQL["title"])
        from_sql = f"""
            FROM board_games g
            LEFT JOIN collection_entries c ON c.board_game_id = g.id
            LEFT JOIN game_metadata_cache m
              ON m.board_game_id = g.id
             AND m.provider = '{METADATA_PROVIDER}'
        """

        with self.database.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS count {from_sql} {where_sql}", params
            ).fetchone()["count"]
            rows = connection.execute(
                f"""
                SELECT g.*, c.coll_id, c.user_rating, c.num_plays, c.own,
                       c.for_trade, c.want, c.want_to_buy, c.want_to_play,
                       c.previously_owned, c.preordered, c.wishlist,
                       c.wishlist_priority, c.barcode, c.version_languages,
                       c.version_publishers, c.version_year_published,
                       c.version_nickname, c.inventory_location, c.quantity,
                       {METADATA_CATALOG_SELECT}
                {from_sql}
                {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

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
                SELECT g.*, c.coll_id, c.user_rating, c.num_plays, c.own,
                       c.for_trade, c.want, c.want_to_buy, c.want_to_play,
                       c.previously_owned, c.preordered, c.wishlist,
                       c.wishlist_priority, c.barcode, c.version_languages,
                       c.version_publishers, c.version_year_published,
                       c.version_nickname, c.inventory_location, c.quantity,
                       {METADATA_CATALOG_SELECT}
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id = g.id
                LEFT JOIN game_metadata_cache m
                  ON m.board_game_id = g.id
                 AND m.provider = '{METADATA_PROVIDER}'
                WHERE g.bgg_id = ?
                ORDER BY c.id
                LIMIT 1
                """,
                (bgg_id,),
            ).fetchone()
        return _game_dict(row) if row else None

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
