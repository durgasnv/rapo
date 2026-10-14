from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.schemas.audit import AuditEntry, AuditPage
from app.services.grouping import owned

DESCRIPTIONS = {
    "event.created": "Event created",
    "event.updated": "Event updated",
    "event.published": "Event published",
    "event.cancelled": "Event cancelled",
    "event.completed": "Event completed",
    "grouping.proposed": "Grouping preview generated",
    "grouping.scheduled": "Scheduled grouping preview generated",
    "teams.finalized": "Teams finalized",
    "team.confirmed": "Team assignment confirmed",
    "team.declined": "Team assignment declined",
    "team.withdrawn": "Participant withdrew from team",
    "team.replace": "Vacancy filled from waitlist",
    "team.continue": "Current team size approved",
    "teams.deadline_extended": "Confirmation deadline extended",
    "teams.reassigned": "Team members reassigned",
    "registration.registered": "Participant registered",
    "registration.waitlisted": "Participant waitlisted",
    "registration.cancelled": "Registration cancelled",
    "demo.seeded": "Demo data seeded",
}
SYSTEM_ACTORS = {"grouping.scheduled": "Scheduled worker", "demo.seeded": "Demo setup"}


def read(db: Session, event_id: UUID, owner: User, offset: int, limit: int) -> AuditPage:
    event = owned(db, event_id, owner, shared=True)
    total = (
        db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.event_id == event.id))
        or 0
    )
    # Select only the public projection, keeping raw snapshots and emails out of the read.
    rows = db.execute(
        select(AuditLog.id, AuditLog.action, AuditLog.created_at, User.name)
        .join(User, User.id == AuditLog.actor_id)
        .where(AuditLog.event_id == event.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    items = [
        AuditEntry(
            id=entry_id,
            action=action if action in DESCRIPTIONS else "other",
            description=DESCRIPTIONS.get(action, "Other event activity"),
            actor_name=SYSTEM_ACTORS.get(action, name),
            created_at=created_at,
        )
        for entry_id, action, created_at, name in rows
    ]
    return AuditPage(items=items, total=total, offset=offset, limit=limit)
