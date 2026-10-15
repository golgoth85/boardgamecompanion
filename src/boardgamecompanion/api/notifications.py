from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from boardgamecompanion.api.common import database
from boardgamecompanion.notifications import NotificationService


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationReadPayload(BaseModel):
    read: bool = True


@router.get("")
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=250),
):
    return NotificationService(database()).list(unread_only=unread_only, limit=limit)


@router.put("/{notification_id}/read")
def set_notification_read(notification_id: str, payload: NotificationReadPayload):
    try:
        return NotificationService(database()).mark_read(notification_id, read=payload.read)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/read-all")
def mark_all_notifications_read():
    return NotificationService(database()).mark_all_read()
