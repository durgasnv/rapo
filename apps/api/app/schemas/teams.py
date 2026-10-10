from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class OwnerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    request_id: UUID


class DeadlineInput(OwnerAction):
    confirmation_deadline: AwareDatetime


class ReassignInput(OwnerAction):
    user_id: UUID
    target_team_id: UUID
    swap_user_id: UUID | None = None


class ConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    team_version: int = Field(ge=1)
    decision: Literal["confirm", "decline"]


class AssignmentOut(BaseModel):
    user_id: UUID
    name: str
    status: str
    confirmed_at: datetime | None


class FinalTeamOut(BaseModel):
    id: UUID
    number: int
    version: int
    target_size: int
    status: Literal["READY", "AWAITING_CONFIRMATIONS", "NEEDS_ATTENTION"]
    reasons: list[str]
    members: list[AssignmentOut]


class RosterOut(BaseModel):
    event_id: UUID
    event_status: str
    version: int
    confirmation_deadline: datetime
    confirmation_open: bool
    withdrawal_open: bool
    own_status: str | None = None
    teams: list[FinalTeamOut]
