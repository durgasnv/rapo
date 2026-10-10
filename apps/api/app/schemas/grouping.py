from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GroupingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    seed: int = Field(default=0, ge=0, le=2147483647)


class MemberOut(BaseModel):
    user_id: UUID
    name: str


class TeamOut(BaseModel):
    number: int
    members: list[MemberOut]
    score: int
    explanation: str


class GroupingOut(BaseModel):
    id: UUID
    event_id: UUID
    status: str
    seed: int
    algorithm_version: str
    score: int
    fairness: int
    baseline_score: int
    baseline_fairness: int
    evaluations: int
    created_at: datetime
    stale: bool
    stale_reason: str | None
    teams: list[TeamOut]
