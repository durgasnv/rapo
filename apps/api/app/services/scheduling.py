from uuid import UUID

from sqlalchemy.orm import Session

from app.models import GroupingJob, User, utcnow
from app.schemas.notifications import GroupingJobOut
from app.services.grouping import owned


def status(db: Session, event_id: UUID, owner: User) -> GroupingJobOut:
    event = owned(db, event_id, owner, shared=True)
    job = db.get(GroupingJob, event.id)
    if event.status not in {"PUBLISHED", "GROUPS_PROPOSED"}:
        return GroupingJobOut(
            status="INACTIVE",
            attempts=job.attempts if job else 0,
            message="Scheduled grouping is inactive for this event.",
        )
    if event.status == "GROUPS_PROPOSED":
        return GroupingJobOut(
            status="SUCCEEDED" if job and job.status == "SUCCEEDED" else "PREVIEW_EXISTS",
            attempts=job.attempts if job else 0,
            message="A preview already exists. Review it or regenerate manually if stale.",
        )
    if utcnow() >= min(event.start_at, event.confirmation_deadline):
        return GroupingJobOut(
            status="EXPIRED",
            attempts=job.attempts if job else 0,
            message="The confirmation or event-start cutoff passed before grouping completed.",
        )
    if job:
        return GroupingJobOut(
            status=job.status,
            attempts=job.attempts,
            message=job.message,
            next_attempt_at=job.next_attempt_at,
            updated_at=job.updated_at,
        )
    return GroupingJobOut(
        status="WAITING" if utcnow() < event.grouping_at else "DUE",
        attempts=0,
        message="Waiting for the grouping time and an active worker.",
    )
