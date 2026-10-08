from __future__ import annotations

from fastapi import APIRouter, Query

from boardgamecompanion.catalog import Catalog
from boardgamecompanion.dependencies import get_database
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
    catalog = Catalog(get_database()).list_games(
        query=query,
        owned=True,
        limit=limit,
        offset=0,
    )
    folded = query.casefold()
    sections = [
        {"key": key, "title": title, "url": url, "description": description}
        for key, title, url, description in SECTIONS
        if folded in title.casefold() or folded in description.casefold()
    ][:6]
    wishlist = [
        item
        for item in WishlistStore(get_database()).list()
        if folded in str(item.get("title") or "").casefold()
    ][:limit]
    return {
        "query": query,
        "groups": {
            "games": catalog["items"],
            "sections": sections,
            "wishlist": wishlist,
            "rulebooks": [],
            "crowdfunding": [],
        },
    }
