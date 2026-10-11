from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_id: UUID
    kind: str
    message: str
    destination: Literal["ACCOUNT", "EVENT", "ORGANIZER"]
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int
    offset: int
    limit: int


class GroupingJobOut(BaseModel):
    status: str
    attempts: int
    message: str
    next_attempt_at: datetime | None = None
    updated_at: datetime | None = None
