from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from boardgamecompanion.dependencies import get_database
from boardgamecompanion.notifications import NotificationNotFound, NotificationStore

router = APIRouter(tags=["notifications"])


class NotificationReadPayload(BaseModel):
    read: bool = True


@router.get("/api/notifications")
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=250),
) -> dict[str, object]:
    return NotificationStore(get_database()).list(
        unread_only=unread_only,
        limit=limit,
    )


@router.patch("/api/notifications/{notification_id}")
def update_notification(
    notification_id: str,
    payload: NotificationReadPayload,
) -> dict[str, object]:
    try:
        return NotificationStore(get_database()).mark_read(
            notification_id,
            read=payload.read,
        )
    except NotificationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
