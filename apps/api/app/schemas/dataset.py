"""Validate fixture relationships before writing any database records."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.events import EventInput

Identifier = Annotated[int, Field(strict=True, ge=1)]
SourceID = Annotated[str, Field(min_length=1, max_length=100)]


class Member(BaseModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: Literal["participant", "organizer"]


class DatasetEvent(EventInput):
    id: SourceID
    organizer_id: Identifier
    status: Literal["DRAFT", "PUBLISHED", "GROUPS_FINALIZED", "COMPLETED"]
    version: int = Field(ge=1)
    registered_count: int = Field(ge=0)
    waitlisted_count: int = Field(ge=0)


class DatasetRegistration(BaseModel):
    event_id: SourceID
    member_id: Identifier
    status: Literal["REGISTERED", "WAITLISTED", "CANCELLED"]
    queue_number: Identifier


class DatasetTeam(BaseModel):
    number: Identifier
    members: list[Identifier] = Field(min_length=1, max_length=1000)


class DatasetRun(BaseModel):
    event_id: SourceID
    status: Literal["FINALIZED"]
    seed: int = Field(ge=0, le=2147483647)
    teams: list[DatasetTeam] = Field(min_length=1)


class DatasetHistory(BaseModel):
    event_id: SourceID
    teams: list[DatasetTeam] = Field(min_length=1)


class DatasetAssignment(BaseModel):
    event_id: SourceID
    team_number: Identifier
    member_id: Identifier
    status: Literal["PENDING", "CONFIRMED", "DECLINED", "WITHDRAWN"]


class Dataset(BaseModel):
    # Documentation metadata and profile fields without an app counterpart are
    # intentionally excluded. JSON roles never grant application privileges.
    model_config = ConfigDict(extra="ignore")
    members: list[Member] = Field(min_length=1, max_length=1000)
    events: list[DatasetEvent] = Field(min_length=1, max_length=100)
    registrations: list[DatasetRegistration] = Field(max_length=10000)
    grouping_runs: list[DatasetRun]
    assignments: list[DatasetAssignment]
    completed_event_history: list[DatasetHistory]

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        members = {m.id: m for m in self.members}
        events = {e.id: e for e in self.events}
        if len(members) != len(self.members) or len(events) != len(self.events):
            raise ValueError("Dataset member and event IDs must be unique")
        if len({str(m.email).lower() for m in self.members}) != len(members):
            raise ValueError("Dataset member emails must be unique")
        for event in self.events:
            owner = members.get(event.organizer_id)
            if owner is None or owner.role != "organizer":
                raise ValueError("Every event must reference a dataset organizer")
        people: dict[str, set[int]] = {key: set() for key in events}
        registered: dict[str, set[int]] = {key: set() for key in events}
        waiting: dict[str, int] = dict.fromkeys(events, 0)
        tickets: set[tuple[str, int]] = set()
        for row in self.registrations:
            member = members.get(row.member_id)
            if row.event_id not in events or member is None or member.role != "participant":
                raise ValueError("Registrations must reference known events and participants")
            key = (row.event_id, row.queue_number)
            if key in tickets or row.member_id in people[row.event_id]:
                raise ValueError("Registration identities and event queue tickets must be unique")
            tickets.add(key)
            people[row.event_id].add(row.member_id)
            if row.status == "REGISTERED":
                registered[row.event_id].add(row.member_id)
            elif row.status == "WAITLISTED":
                waiting[row.event_id] += 1
        for event in self.events:
            count = len(registered[event.id])
            if count != event.registered_count or waiting[event.id] != event.waitlisted_count:
                raise ValueError("Event summary counts must match source registrations")
            if event.capacity is not None and count > event.capacity:
                raise ValueError("Registrations exceed event capacity")
            if event.status == "DRAFT" and people[event.id]:
                raise ValueError("Draft events cannot have registrations")
        histories = {h.event_id: h for h in self.completed_event_history}
        runs = {r.event_id: r for r in self.grouping_runs}
        if len(histories) != len(self.completed_event_history) or len(runs) != len(
            self.grouping_runs
        ):
            raise ValueError("An event may have only one imported grouping")
        if histories.keys() & runs.keys() or (histories.keys() | runs.keys()) - events.keys():
            raise ValueError("Grouping sources must reference distinct known events")
        groups = {}
        for event in self.events:
            source = histories.get(event.id) or runs.get(event.id)
            if (event.status == "COMPLETED") != (event.id in histories) or (
                event.status == "GROUPS_FINALIZED"
            ) != (event.id in runs):
                raise ValueError("Completed and finalized events require matching grouping data")
            if source is None:
                continue
            mapping = {}
            numbers = set()
            for team in source.teams:
                if team.number in numbers or not (
                    event.min_team_size <= len(team.members) <= event.max_team_size
                ):
                    raise ValueError("Team numbers must be unique and sizes must be valid")
                numbers.add(team.number)
                for person in team.members:
                    if person in mapping or person not in registered[event.id]:
                        raise ValueError("Teams must contain distinct registered participants")
                    mapping[person] = team.number
            if set(mapping) != registered[event.id]:
                raise ValueError("Each registered participant must belong to one imported team")
            groups[event.id] = mapping
        assigned: set[tuple[str, int]] = set()
        for assignment in self.assignments:
            key = (assignment.event_id, assignment.member_id)
            if (
                assignment.event_id not in runs
                or key in assigned
                or groups[assignment.event_id].get(assignment.member_id) != assignment.team_number
            ):
                raise ValueError("Assignments must uniquely match the finalized preview")
            assigned.add(key)
        if assigned != {(event_id, person) for event_id in runs for person in groups[event_id]}:
            raise ValueError("Every finalized team member requires an assignment")
        return self
