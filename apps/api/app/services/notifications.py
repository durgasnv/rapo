from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Assignment, Event, FinalTeam, Notification, Registration, utcnow
from app.schemas.notifications import NotificationOut, NotificationPage


def send(
    db: Session,
    event: Event,
    user_id: UUID,
    kind: str,
    message: str,
    key: str,
    *,
    destination: str | None = None,
) -> None:
    db.execute(
        insert(Notification)
        .values(
            user_id=user_id,
            event_id=event.id,
            kind=kind,
            message=f"{event.title}: {message}",
            dedup_key=key,
            destination=destination or ("ORGANIZER" if user_id == event.organizer_id else "EVENT"),
        )
        .on_conflict_do_nothing(constraint="notification_user_key")
    )


def page(
    db: Session, user_id: UUID, offset: int, limit: int, unread_only: bool
) -> NotificationPage:
    query = select(Notification).where(Notification.user_id == user_id)
    unread = (
        db.scalar(
            select(func.count()).select_from(query.where(Notification.read_at.is_(None)).subquery())
        )
        or 0
    )
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return NotificationPage(
        items=[NotificationOut.model_validate(row) for row in rows],
        total=total,
        unread_count=unread,
        offset=offset,
        limit=limit,
    )


def mark_read(db: Session, user_id: UUID, notification_id: UUID) -> NotificationOut:
    row = db.scalar(
        select(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Notification not found")
    if row.read_at is None:
        row.read_at = utcnow()
    db.flush()
    return NotificationOut.model_validate(row)


def roster_change(db: Session, event: Event, action: str, before: dict[str, object]) -> None:
    # Use a fresh ORM query for typed memberships; snapshots identify which consent changed.
    active = {"PENDING", "CONFIRMED"}
    previous_members = before["members"]
    previous_teams = before["teams"]
    assert isinstance(previous_members, list) and isinstance(previous_teams, list)
    old_members = {m["user_id"]: m for m in previous_members}
    old_versions = {t["id"]: t["version"] for t in previous_teams}
    key = f"roster:{event.id}:{event.version}"
    for member, version in db.execute(
        select(Assignment, FinalTeam.version)
        .join(FinalTeam, FinalTeam.id == Assignment.team_id)
        .where(Assignment.event_id == event.id)
    ):
        old = old_members.get(str(member.user_id))
        if member.status in active:
            if old is None:
                send(
                    db,
                    event,
                    member.user_id,
                    "TEAM_ASSIGNED",
                    "Your team is assigned. Review and confirm it before the deadline.",
                    key + ":assigned",
                )
            elif action == "teams.deadline_extended":
                send(
                    db,
                    event,
                    member.user_id,
                    "DEADLINE_EXTENDED",
                    "The deadline was extended. Review your team for the new deadline.",
                    key + ":deadline",
                )
            elif (
                old["team_id"] != str(member.team_id)
                or old_versions.get(str(member.team_id)) != version
            ):
                send(
                    db,
                    event,
                    member.user_id,
                    "TEAM_CHANGED",
                    "Your teammates changed. Review your team and confirm again.",
                    key + ":changed",
                )
        elif old and old["status"] in active:
            send(
                db,
                event,
                member.user_id,
                "ASSIGNMENT_ENDED",
                "Your team assignment ended.",
                key + ":ended",
                destination="ACCOUNT",
            )
    messages = {
        "teams.finalized": "Teams are finalized and awaiting participant confirmations.",
        "team.confirmed": "A participant confirmed their team.",
        "team.declined": "A participant declined. Review the team vacancy.",
        "team.withdrawn": "A participant withdrew. Review your roster and any vacancy.",
        "team.replace": "A waitlisted participant filled a team vacancy.",
        "team.continue": "The current team size was approved.",
        "teams.reassigned": "Participants were reassigned and must confirm again.",
        "teams.deadline_extended": "The confirmation deadline was extended.",
    }
    send(db, event, event.organizer_id, "ROSTER_UPDATED", messages[action], key + ":owner")


def cancelled(db: Session, event: Event) -> None:
    for user_id in db.scalars(
        select(Registration.user_id).where(
            Registration.event_id == event.id,
            Registration.status.in_(["REGISTERED", "WAITLISTED"]),
        )
    ):
        send(
            db,
            event,
            user_id,
            "EVENT_CANCELLED",
            "The event was cancelled.",
            f"cancel:{event.id}",
            destination="ACCOUNT",
        )
