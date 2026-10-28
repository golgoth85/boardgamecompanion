from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from boardgamecompanion.dependencies import get_database
from boardgamecompanion.price_search import PriceSearchError, best_offer
from boardgamecompanion.bgg_metadata import BggMetadataStore
from boardgamecompanion.bgg_reference import BggReferenceCatalog
from boardgamecompanion.catalog import Catalog
from boardgamecompanion.gameplay_summary import GameplaySummaryService
from boardgamecompanion.service_factories import get_crowdfunding_service, get_price_provider
from boardgamecompanion.wishlist import WishlistError, WishlistNotFound, WishlistStore

router = APIRouter(tags=["wishlist"])
LOGGER = logging.getLogger(__name__)


class WishlistPayload(BaseModel):
    source_kind: str = Field(min_length=1, max_length=32)
    source_key: str = Field(min_length=1, max_length=500)
    bgg_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=500)
    year_published: int | None = Field(default=None, ge=1000, le=3000)
    cover_url: str | None = Field(default=None, max_length=2000)
    target_url: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/api/wishlist")
def list_wishlist() -> dict[str, object]:
    database = get_database()
    items = WishlistStore(database).list()
    try:
        _attach_current_data(database, items)
    except Exception:  # the wishlist stays readable even if enrichment fails
        LOGGER.exception("Wishlist enrichment failed")
    return {"items": items, "total": len(items)}


def _game_from_reference(detail: dict[str, Any]) -> dict[str, Any]:
    details = detail.get("details") or {}
    return {
        "bgg_id": detail["bgg_id"],
        "title": detail["name"],
        "year_published": detail.get("year_published"),
        "players": {"min": details.get("min_players"), "max": details.get("max_players")},
        "play_time": {
            "playing": details.get("playing_time"),
            "min": details.get("min_play_time"),
            "max": details.get("max_play_time"),
        },
        "bgg": {
            "average": detail.get("average"),
            "users_rated": detail.get("users_rated"),
            "rank": detail.get("rank"),
            "average_weight": details.get("bgg_average_weight"),
            "recommended_age": details.get("bgg_recommended_age"),
            "best_players": details.get("bgg_best_players"),
            "recommended_players": details.get("bgg_recommended_players"),
            "language_dependence": details.get("bgg_language_dependence"),
        },
        "categories": list(details.get("categories") or [])[:6],
        "mechanics": list(details.get("mechanics") or [])[:6],
        "has_description": bool(str(detail.get("description") or "").strip()),
        "owned": bool(detail.get("owned")),
    }


def _attach_current_data(database, items: list[dict[str, Any]]) -> None:
    """Current BGG/library facts, gameplay summary and campaign state for each item.

    The wishlist row only keeps what was known when the title was saved; the
    card shows the data the rest of the app shows today.
    """
    catalog = Catalog(database)
    reference = BggReferenceCatalog(database)
    bgg_ids = [int(item["bgg_id"]) for item in items if item.get("bgg_id")]
    summaries = GameplaySummaryService(database).get_cached_many(bgg_ids) if bgg_ids else {}
    for item in items:
        if not item.get("bgg_id"):
            continue
        bgg_id = int(item["bgg_id"])
        game = None
        library = catalog.get_game(bgg_id)
        if library is not None:
            metadata = BggMetadataStore(database, None).get(bgg_id) or {}
            game = {
                **{key: library.get(key) for key in ("bgg_id", "title", "year_published", "players", "play_time", "bgg")},
                "categories": list(metadata.get("categories") or [])[:6],
                "mechanics": list((metadata.get("metadata") or {}).get("mechanics") or [])[:6],
                "has_description": bool(str(metadata.get("description") or "").strip()),
                "owned": bool((library.get("collection") or {}).get("own")),
            }
        else:
            detail = reference.detail(bgg_id)
            if detail is not None:
                game = _game_from_reference(detail)
        if game is not None:
            summary = summaries.get(bgg_id)
            game["gameplay_summary"] = summary["summary"] if summary else None
            item["game"] = game

    campaigns = {}
    if any(item.get("source_kind") == "crowdfunding" for item in items):
        service = get_crowdfunding_service()
        now = datetime.now(UTC)
        for campaign in service.cached_campaigns():
            decorated = service._decorate(campaign, rates={"EUR": 1.0}, now=now)
            for key in (campaign.get("project_url"), campaign.get("id")):
                if key:
                    campaigns[str(key)] = decorated
    for item in items:
        if item.get("source_kind") != "crowdfunding":
            continue
        campaign = campaigns.get(str(item.get("source_key") or "")) or campaigns.get(str(item.get("target_url") or ""))
        if campaign:
            item["campaign"] = {
                key: campaign.get(key)
                for key in (
                    "status", "remaining_seconds", "funding_percent", "funds", "currency",
                    "backer_count", "creator", "description", "platform",
                )
            }


@router.post("/api/wishlist", status_code=201)
def add_wishlist_item(payload: WishlistPayload) -> dict[str, object]:
    try:
        return WishlistStore(get_database()).upsert(**payload.model_dump())
    except WishlistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/wishlist/{item_id}/prices")
def refresh_wishlist_prices(item_id: str) -> dict[str, object]:
    store = WishlistStore(get_database())
    try:
        item = store.get(item_id)
    except WishlistNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    provider = get_price_provider()
    if provider is None:
        raise HTTPException(
            status_code=409,
            detail="Configura la chiave del provider di ricerca web nelle impostazioni AI per cercare i prezzi.",
        )
    alternate_titles: tuple[str, ...] = ()
    if item.get("bgg_id"):
        reference = BggReferenceCatalog(get_database()).detail(int(item["bgg_id"]))
        if reference:
            alternate_titles = tuple(reference["alternate_names"])
    try:
        offers = provider.search(title=item["title"], year=item["year_published"], alternate_titles=alternate_titles)
    except PriceSearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return store.set_prices(item_id, offers=offers, best=best_offer(offers))


@router.delete("/api/wishlist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_wishlist_item(item_id: str) -> Response:
    try:
        WishlistStore(get_database()).delete(item_id)
    except WishlistNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
