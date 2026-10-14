from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditEntry(BaseModel):
    id: UUID
    action: str
    description: str
    actor_name: str
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    offset: int
    limit: int
