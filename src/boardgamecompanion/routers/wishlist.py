from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from boardgamecompanion.dependencies import get_database
from boardgamecompanion.price_search import PriceSearchError, best_offer
from boardgamecompanion.service_factories import get_price_provider
from boardgamecompanion.wishlist import WishlistError, WishlistNotFound, WishlistStore

router = APIRouter(tags=["wishlist"])


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
    items = WishlistStore(get_database()).list()
    return {"items": items, "total": len(items)}


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
            detail="Configura la chiave Gemini nelle impostazioni per cercare i prezzi.",
        )
    try:
        offers = provider.search(title=item["title"], year=item["year_published"])
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
