from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from boardgamecompanion.api.common import database
from boardgamecompanion.wishlist import WishlistError, WishlistService


router = APIRouter(prefix="/api/wishlist", tags=["wishlist"])


class WishlistPayload(BaseModel):
    source_type: Literal["suggestion", "crowdfunding", "bgg", "manual"]
    source_key: str | None = Field(default=None, max_length=1000)
    bgg_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=500)
    year_published: int | None = Field(default=None, ge=1000, le=3000)
    cover_url: str | None = Field(default=None, max_length=2000)
    target_url: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def get_wishlist():
    service = WishlistService(database())
    items = service.list()
    return {"items": items, "count": len(items)}


@router.post("", status_code=201)
def add_wishlist_item(payload: WishlistPayload):
    try:
        return WishlistService(database()).upsert(**payload.model_dump())
    except WishlistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{item_id}", status_code=204)
def remove_wishlist_item(item_id: str):
    try:
        WishlistService(database()).remove(item_id)
    except WishlistError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return None
