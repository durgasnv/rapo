from datetime import datetime, timedelta
from typing import Annotated, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
]


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    title: Title
    description: Description
    location: str = Field(default="", max_length=500)
    timezone: str = Field(max_length=100)
    start_at: AwareDatetime
    end_at: AwareDatetime
    registration_opens_at: AwareDatetime
    registration_closes_at: AwareDatetime
    grouping_at: AwareDatetime | None = None
    confirmation_deadline: AwareDatetime
    capacity: int | None = Field(default=None, ge=1)
    min_team_size: int = Field(ge=1, le=1000)
    max_team_size: int = Field(ge=1, le=1000)

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use a valid IANA timezone, such as Asia/Kolkata") from error
        if self.max_team_size < self.min_team_size:
            raise ValueError("Maximum team size must be at least the minimum")
        if self.capacity is not None and self.capacity < self.min_team_size:
            raise ValueError("Capacity must fit at least one valid team")
        if (
            not self.registration_opens_at
            < self.registration_closes_at
            <= self.start_at
            < self.end_at
        ):
            raise ValueError("Required order: registration opens < closes <= event start < end")
        if self.grouping_at is None:
            # Clamp the interval before subtracting so valid early dates cannot
            # underflow datetime's lower bound.
            lead_time = min(timedelta(days=3), self.start_at - self.registration_closes_at)
            self.grouping_at = self.start_at - lead_time
        if (
            not self.registration_closes_at
            <= self.grouping_at
            <= self.confirmation_deadline
            <= self.start_at
        ):
            raise ValueError(
                "Required order: registration closes <= grouping "
                "<= confirmation deadline <= event start"
            )
        return self


class EventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    description: Description | None = None
    location: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=100)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    registration_opens_at: AwareDatetime | None = None
    registration_closes_at: AwareDatetime | None = None
    grouping_at: AwareDatetime | None = None
    confirmation_deadline: AwareDatetime | None = None
    capacity: int | None = Field(default=None, ge=1)
    min_team_size: int | None = Field(default=None, ge=1, le=1000)
    max_team_size: int | None = Field(default=None, ge=1, le=1000)
    version: int = Field(ge=1)


class EventOut(EventInput):
    id: UUID
    organizer_id: UUID
    status: str
    version: int
    created_at: datetime


class EventPage(BaseModel):
    items: list[EventOut]
    total: int
    offset: int
    limit: int


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
