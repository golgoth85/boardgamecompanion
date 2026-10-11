from __future__ import annotations

from fastapi import APIRouter, Query

from boardgamecompanion.catalog import (
    Catalog,
    game_title_search_clause,
    game_title_search_params,
)
from boardgamecompanion.dependencies import get_database
from boardgamecompanion.game_lists import GameListStore
from boardgamecompanion.service_factories import get_crowdfunding_service
from boardgamecompanion.wishlist import WishlistStore

router = APIRouter(tags=["search"])

SECTIONS = (
    ("catalog", "Catalogo", "/", "La tua ludoteca"),
    ("explore", "Esplora", "/explore", "Generi e meccaniche"),
    ("rankings", "Classifiche", "/rankings", "Classifiche della collezione"),
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
    catalog = Catalog(database).list_games(
        query=query,
        limit=limit,
        offset=0,
    )
    with database.connect() as connection:
        matched_game_rows = connection.execute(
            f"""
            SELECT DISTINCT g.bgg_id
            FROM board_games g
            LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
            WHERE {game_title_search_clause()}
            LIMIT 250
            """,
            game_title_search_params(query),
        ).fetchall()
    matched_game_ids = {int(row["bgg_id"]) for row in matched_game_rows}

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
                str(item.get("bgg_id") or "").isdigit()
                and int(item["bgg_id"]) in matched_game_ids
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
        document_rows = connection.execute(
            f"""
            SELECT d.id, g.bgg_id, g.title AS game_title,
                   d.title AS title, d.language
            FROM game_documents d
            JOIN board_games g ON g.id=d.board_game_id
            LEFT JOIN board_game_enrichments e ON e.board_game_id=g.id
            WHERE d.document_type='rulebook'
              AND (
                  {game_title_search_clause()}
                  OR instr(lower(COALESCE(d.title,'')),lower(?))>0
                  OR instr(lower(d.original_filename),lower(?))>0
              )
            ORDER BY d.is_official DESC,
                     CASE WHEN d.language='it' THEN 0 ELSE 1 END,
                     d.created_at DESC
            LIMIT ?
            """,
            (
                *game_title_search_params(query),
                query,
                query,
                limit,
            ),
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
        if (
            folded in str(item.get("title") or "").casefold()
            or (
                str(item.get("related_bgg_id") or "").isdigit()
                and int(item["related_bgg_id"]) in matched_game_ids
            )
        )
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
