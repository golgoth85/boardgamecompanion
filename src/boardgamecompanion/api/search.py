from fastapi import APIRouter, Query

from boardgamecompanion.api.common import database
from boardgamecompanion.universal_search import UniversalSearchService


router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def universal_search(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=12, ge=1, le=30),
):
    return UniversalSearchService(database()).search(q, limit=limit)
