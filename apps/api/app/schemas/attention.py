from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AttentionEvent(BaseModel):
    event_id: UUID
    title: str
    start_at: datetime
    timezone: str
    status: str
    reasons: list[str]


class AttentionPage(BaseModel):
    items: list[AttentionEvent]
    total: int
    offset: int
    limit: int
