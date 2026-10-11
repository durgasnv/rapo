from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.schemas.notifications import NotificationOut, NotificationPage
from app.security import CurrentIdentity, Db
from app.services import notifications

router = APIRouter(tags=["notifications"])


@router.get("/me/notifications", response_model=NotificationPage)
def list_notifications(
    identity: CurrentIdentity,
    db: Db,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    unread_only: bool = False,
) -> NotificationPage:
    return notifications.page(db, identity.user.id, offset, limit, unread_only)


@router.post("/me/notifications/{notification_id}/read", response_model=NotificationOut)
def read_notification(notification_id: UUID, identity: CurrentIdentity, db: Db) -> NotificationOut:
    return notifications.mark_read(db, identity.user.id, notification_id)
