from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.schemas.grouping import GroupingInput, GroupingOut
from app.schemas.notifications import GroupingJobOut
from app.security import Db, Organizer
from app.services import grouping, scheduling
from app.services.grouping_engine import GroupingError

router = APIRouter(tags=["grouping"])


@router.post("/events/{event_id}/grouping-runs", response_model=GroupingOut)
def create_preview(
    event_id: UUID, body: GroupingInput, organizer: Organizer, db: Db
) -> GroupingOut:
    try:
        return grouping.create(db, event_id, organizer, body)
    except GroupingError as error:
        raise HTTPException(422, {"code": error.code, "message": str(error)}) from error


@router.get("/events/{event_id}/grouping-runs/latest", response_model=GroupingOut | None)
def latest_preview(event_id: UUID, organizer: Organizer, db: Db) -> GroupingOut | None:
    return grouping.read(db, event_id, organizer, None)


@router.get("/events/{event_id}/grouping-runs/{run_id}", response_model=GroupingOut)
def get_preview(event_id: UUID, run_id: UUID, organizer: Organizer, db: Db) -> GroupingOut:
    result = grouping.read(db, event_id, organizer, run_id)
    assert result is not None
    return result


@router.get("/events/{event_id}/grouping-job", response_model=GroupingJobOut)
def scheduled_status(event_id: UUID, organizer: Organizer, db: Db) -> GroupingJobOut:
    return scheduling.status(db, event_id, organizer)
