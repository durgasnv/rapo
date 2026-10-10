import csv
import io
from uuid import UUID

from fastapi import APIRouter, Response

from app.schemas.events import VersionInput
from app.schemas.teams import (
    ConfirmationInput,
    DeadlineInput,
    OwnerAction,
    ReassignInput,
    RosterOut,
)
from app.security import CurrentIdentity, Db, Organizer
from app.services import teams
from app.services.grouping import owned
from app.services.registrations import lock_event

router = APIRouter(tags=["teams"])


@router.post("/events/{event_id}/grouping-runs/{run_id}/finalize", response_model=RosterOut)
def finalize(
    event_id: UUID, run_id: UUID, body: VersionInput, owner: Organizer, db: Db
) -> RosterOut:
    return teams.finalize(db, event_id, run_id, owner, body.version)


@router.get("/events/{event_id}/teams", response_model=RosterOut)
def roster(event_id: UUID, identity: CurrentIdentity, db: Db) -> RosterOut:
    event = lock_event(db, event_id, shared=True)
    return teams.roster(db, event, identity.user)


@router.post("/events/{event_id}/teams/{team_id}/confirm", response_model=RosterOut)
def confirm(
    event_id: UUID, team_id: UUID, body: ConfirmationInput, identity: CurrentIdentity, db: Db
) -> RosterOut:
    return teams.confirm(db, event_id, team_id, identity.user, body)


@router.post("/events/{event_id}/teams/withdraw", response_model=RosterOut)
def withdraw(event_id: UUID, identity: CurrentIdentity, db: Db) -> RosterOut:
    return teams.withdraw(db, event_id, identity.user)


@router.post("/events/{event_id}/teams/{team_id}/replace", response_model=RosterOut)
def replace(
    event_id: UUID, team_id: UUID, body: OwnerAction, owner: Organizer, db: Db
) -> RosterOut:
    return teams.repair(db, event_id, team_id, owner, body, "replace")


@router.post("/events/{event_id}/teams/{team_id}/continue", response_model=RosterOut)
def approve_continuation(
    event_id: UUID, team_id: UUID, body: OwnerAction, owner: Organizer, db: Db
) -> RosterOut:
    return teams.repair(db, event_id, team_id, owner, body, "continue")


@router.post("/events/{event_id}/teams/reassign", response_model=RosterOut)
def reassign(event_id: UUID, body: ReassignInput, owner: Organizer, db: Db) -> RosterOut:
    return teams.reassign(db, event_id, owner, body)


@router.post("/events/{event_id}/teams/deadline", response_model=RosterOut)
def deadline(event_id: UUID, body: DeadlineInput, owner: Organizer, db: Db) -> RosterOut:
    return teams.extend_deadline(db, event_id, owner, body)


def spreadsheet_cell(value: str) -> str:
    # CSV quoting alone does not prevent spreadsheet formula execution.
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))
        else value
    )


@router.get("/events/{event_id}/teams/export")
def export(event_id: UUID, owner: Organizer, db: Db) -> Response:
    event = owned(db, event_id, owner, shared=True)
    roster = teams.roster(db, event, owner)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
    writer.writerow(["team", "team_status", "participant_id", "name", "confirmation_status"])
    for team in roster.teams:
        for member in team.members:
            writer.writerow(
                [
                    team.number,
                    team.status,
                    str(member.user_id),
                    spreadsheet_cell(member.name),
                    member.status,
                ]
            )
    return Response(
        stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rapo-{event.id}-teams.csv"'},
    )
