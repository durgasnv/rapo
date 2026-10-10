from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models import RegistrationStatus
from app.schemas.events import EventOut


class RegistrationOut(BaseModel):
    id: UUID
    event_id: UUID
    status: RegistrationStatus
    registered_at: datetime
    waitlist_position: int | None


class RegistrationState(BaseModel):
    registration: RegistrationOut | None
    registered_count: int
    waitlisted_count: int
    capacity: int | None
    registration_open: bool
    withdrawal_open: bool
    event_status: str


class MyRegistration(RegistrationOut):
    event: EventOut


class MyRegistrationPage(BaseModel):
    items: list[MyRegistration]
    total: int
    offset: int
    limit: int


class RosterRegistration(RegistrationOut):
    user_id: UUID
    name: str


class RosterPage(BaseModel):
    items: list[RosterRegistration]
    total: int
    offset: int
    limit: int
    registered_count: int
    waitlisted_count: int
