from __future__ import annotations

from fastapi import APIRouter, Query

from boardgamecompanion.catalog import Catalog
from boardgamecompanion.dependencies import get_database
from boardgamecompanion.game_lists import GameListStore
from boardgamecompanion.service_factories import get_crowdfunding_service
from boardgamecompanion.wishlist import WishlistStore

router = APIRouter(tags=["search"])

SECTIONS = (
    ("catalog", "Ludoteca", "/", "I giochi della tua collezione"),
    ("bgg", "Catalogo", "/bgg", "Catalogo di riferimento BoardGameGeek"),
    ("explore", "Esplora", "/explore", "Generi e meccaniche"),
    ("rankings", "Classifiche", "/rankings", "Classifiche di ludoteca e catalogo"),
    ("suggestions", "Suggerimenti", "/suggestions", "Giochi consigliati"),
    ("crowdfunding", "Crowdfunding", "/crowdfunding", "Campagne attive"),
    ("lists", "Liste", "/lists", "Liste personali e dinamiche"),
    ("wishlist", "Wishlist", "/wishlist", "Giochi che vuoi tenere d'occhio"),
    ("completed", "Sala dei trofei", "/completed", "Giochi giocati e completati"),
)


@router.get("/api/search")
def universal_search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=8, ge=1, le=30),
) -> dict[str, object]:
    query = q.strip()
    if not query:
        return {
            "query": query,
            "groups": {
                "games": [], "sections": [], "wishlist": [],
                "lists": [], "rulebooks": [], "crowdfunding": [],
            },
        }
    database = get_database()
    database.initialize()
    folded = query.casefold()
    catalog_matches = Catalog(database).list_games(
        query=query,
        limit=200,
        offset=0,
    )
    matched_bgg_ids = {
        int(item["bgg_id"])
        for item in catalog_matches["items"]
        if item.get("bgg_id") is not None
    }
    catalog = {
        **catalog_matches,
        "items": catalog_matches["items"][:limit],
        "limit": limit,
    }
    sections = [
        {"key": key, "title": title, "url": url, "description": description}
        for key, title, url, description in SECTIONS
        if folded in title.casefold() or folded in description.casefold()
    ][:6]
    wishlist = [
        item
        for item in WishlistStore(database).list()
        if (
            folded in str(item.get("title") or "").casefold()
            or (
                item.get("bgg_id") is not None
                and int(item["bgg_id"]) in matched_bgg_ids
            )
        )
    ][:limit]
    lists = [
        item
        for item in GameListStore(database).list()
        if folded in str(item.get("name") or "").casefold()
    ][:limit]

    # Search persisted manuals, not merely the game titles in the catalog.
    # Bound params avoid treating a user-supplied '%' or '_' as a wildcard.
    with database.connect() as connection:
        rulebook_params: list[object] = [query, query, query]
        alias_clause = ""
        if matched_bgg_ids:
            placeholders = ",".join("?" for _ in matched_bgg_ids)
            alias_clause = f" OR g.bgg_id IN ({placeholders})"
            rulebook_params.extend(sorted(matched_bgg_ids))
        rulebook_params.append(limit)
        document_rows = connection.execute(
            f"""
            SELECT d.id, g.bgg_id, g.title AS game_title,
                   d.title AS title, d.language
            FROM game_documents d
            JOIN board_games g ON g.id=d.board_game_id
            WHERE d.document_type='rulebook'
              AND (
                  instr(lower(g.title),lower(?))>0
                  OR instr(lower(COALESCE(d.title,'')),lower(?))>0
                  OR instr(lower(d.original_filename),lower(?))>0
                  {alias_clause}
              )
            ORDER BY d.is_official DESC,
                     CASE WHEN d.language='it' THEN 0 ELSE 1 END,
                     d.created_at DESC
            LIMIT ?
            """,
            rulebook_params,
        ).fetchall()
    rulebooks = [
        {
            "id": row["id"],
            "bgg_id": int(row["bgg_id"]),
            "game_title": row["game_title"],
            "title": row["title"],
            "language": row["language"],
            "url": f"/api/documents/{row['id']}/file",
        }
        for row in document_rows
    ]

    # Never invoke crowdfunding providers from a keypress: only cached data.
    crowdfunding = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "platform": item.get("platform"),
            "project_url": item.get("project_url"),
        }
        for item in get_crowdfunding_service().cached_campaigns()
        if folded in str(item.get("title") or "").casefold()
    ][:limit]

    return {
        "query": query,
        "groups": {
            "games": catalog["items"],
            "sections": sections,
            "wishlist": wishlist,
            "lists": lists,
            "rulebooks": rulebooks,
            "crowdfunding": crowdfunding,
        },
    }
