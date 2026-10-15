from __future__ import annotations

from typing import Any

from boardgamecompanion.database import Database


SECTIONS = (
    ("Catalogo", "/", "catalog"),
    ("Esplora", "/explore", "explore"),
    ("Classifiche", "/rankings", "rankings"),
    ("Suggerimenti", "/suggestions", "suggestions"),
    ("Crowdfunding", "/crowdfunding", "crowdfunding"),
    ("Sala dei trofei", "/completed", "trophies"),
    ("Liste", "/lists", "lists"),
    ("Wishlist", "/wishlist", "wishlist"),
)


class UniversalSearchService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def search(self, query: str, *, limit: int = 12) -> dict[str, Any]:
        needle = str(query or "").strip()
        if not needle:
            return {"query": "", "groups": []}
        cap = max(1, min(int(limit), 30))
        wildcard = f"%{needle}%"
        groups: list[dict[str, Any]] = []

        with self.database.connect() as connection:
            games = connection.execute(
                """
                SELECT g.bgg_id,g.title,g.year_published,e.cover_url,
                       MAX(COALESCE(c.own,0)) AS owned
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
                WHERE g.title LIKE ? COLLATE NOCASE
                   OR g.original_title LIKE ? COLLATE NOCASE
                GROUP BY g.id
                ORDER BY owned DESC,g.title COLLATE NOCASE
                LIMIT ?
                """,
                (wildcard, wildcard, cap),
            ).fetchall()
            wishlist = connection.execute(
                """
                SELECT id,title,bgg_id,cover_url,target_url
                FROM wishlist_items
                WHERE title LIKE ? COLLATE NOCASE
                ORDER BY title COLLATE NOCASE
                LIMIT ?
                """,
                (wildcard, cap),
            ).fetchall()
            lists = connection.execute(
                """
                SELECT id,name,kind FROM game_lists
                WHERE name LIKE ? COLLATE NOCASE
                ORDER BY name COLLATE NOCASE
                LIMIT ?
                """,
                (wildcard, cap),
            ).fetchall()

        if games:
            groups.append(
                {
                    "type": "games",
                    "label": "Giochi",
                    "items": [
                        {
                            "id": f"game:{row['bgg_id']}",
                            "title": row["title"],
                            "subtitle": (
                                ("Posseduto · " if row["owned"] else "")
                                + (str(row["year_published"]) if row["year_published"] else "BGG")
                            ),
                            "url": f"/games/{int(row['bgg_id'])}",
                            "cover_url": row["cover_url"],
                        }
                        for row in games
                    ],
                }
            )

        section_matches = [
            {"id": f"section:{key}", "title": title, "subtitle": "Sezione", "url": url}
            for title, url, key in SECTIONS
            if needle.casefold() in title.casefold()
        ]
        section_matches.extend(
            {
                "id": f"list:{row['id']}",
                "title": row["name"],
                "subtitle": "Lista dinamica" if row["kind"] == "dynamic" else "Lista manuale",
                "url": f"/lists/{row['id']}",
            }
            for row in lists
        )
        if section_matches:
            groups.append({"type": "navigation", "label": "Sezioni e liste", "items": section_matches[:cap]})

        if wishlist:
            groups.append(
                {
                    "type": "wishlist",
                    "label": "Wishlist",
                    "items": [
                        {
                            "id": f"wishlist:{row['id']}",
                            "title": row["title"],
                            "subtitle": "Wishlist",
                            "url": (
                                f"/games/{int(row['bgg_id'])}"
                                if row["bgg_id"] is not None
                                else row["target_url"] or "/wishlist"
                            ),
                            "external": row["bgg_id"] is None and bool(row["target_url"]),
                            "cover_url": row["cover_url"],
                        }
                        for row in wishlist
                    ],
                }
            )
        return {"query": needle, "groups": groups}
