from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Event, FinalTeam, GroupingRun, User, utcnow
from app.services.grouping import owned


def complete(db: Session, event_id: UUID, organizer: User, version: int) -> Event:
    event = owned(db, event_id, organizer)
    # A lost response or competing completion must not produce another audit entry.
    if event.status == "COMPLETED":
        return event
    if event.version != version:
        raise HTTPException(409, "This event changed. Refresh before completing it.")
    if event.status not in {"GROUPS_FINALIZED", "IN_PROGRESS"}:
        raise HTTPException(409, "Only events with finalized teams can be completed")
    if utcnow() < event.end_at:
        raise HTTPException(409, "The event must end before it can be completed")
    finalized = db.scalar(
        select(FinalTeam.id)
        .join(GroupingRun, GroupingRun.id == FinalTeam.run_id)
        .where(FinalTeam.event_id == event.id, GroupingRun.status == "FINALIZED")
        .limit(1)
    )
    if finalized is None:
        raise HTTPException(409, "This event has no finalized roster to complete")
    before = {"status": event.status, "version": event.version}
    event.status = "COMPLETED"
    event.version += 1
    db.add(
        AuditLog(
            actor_id=organizer.id,
            event_id=event.id,
            action="event.completed",
            before_json=before,
            after_json={"status": event.status, "version": event.version},
        )
    )
    # History is derived from the retained final assignments, never an incremented counter.
    db.flush()
    return event
