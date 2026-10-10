from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Event, Registration, RegistrationStatus, utcnow
from app.schemas.registrations import RegistrationOut, RegistrationState


def lock_event(db: Session, event_id: UUID, *, shared: bool = False) -> Event:
    # All joins, withdrawals, promotions, and event cancellation use this same lock.
    event = db.scalar(select(Event).where(Event.id == event_id).with_for_update(read=shared))
    if event is None:
        raise HTTPException(404, "Event not found")
    return event


def find_registration(db: Session, event: Event, user_id: UUID) -> Registration | None:
    return db.scalar(
        select(Registration).where(
            Registration.event_id == event.id, Registration.user_id == user_id
        )
    )


def counts(db: Session, event: Event) -> tuple[int, int]:
    totals = {
        status: total
        for status, total in db.execute(
            select(Registration.status, func.count())
            .where(Registration.event_id == event.id)
            .group_by(Registration.status)
        )
    }
    return totals.get("REGISTERED", 0), totals.get("WAITLISTED", 0)


def registration_out(registration: Registration, position: int | None = None) -> RegistrationOut:
    return RegistrationOut(
        id=registration.id,
        event_id=registration.event_id,
        status=registration.status,
        registered_at=registration.registered_at,
        waitlist_position=position if registration.status == "WAITLISTED" else None,
    )


def state(db: Session, event: Event, registration: Registration | None) -> RegistrationState:
    registered, waiting = counts(db, event)
    position = None
    if registration is not None and registration.status == "WAITLISTED":
        position = db.scalar(
            select(func.count())
            .select_from(Registration)
            .where(
                Registration.event_id == event.id,
                Registration.status == "WAITLISTED",
                Registration.queue_number <= registration.queue_number,
            )
        )
    now = utcnow()
    return RegistrationState(
        registration=registration_out(registration, position) if registration else None,
        registered_count=registered,
        waitlisted_count=waiting,
        capacity=event.capacity,
        registration_open=event.status == "PUBLISHED"
        and event.registration_opens_at <= now < event.registration_closes_at,
        withdrawal_open=event.status in {"PUBLISHED", "GROUPS_PROPOSED", "GROUPS_FINALIZED"}
        and now < event.start_at,
        event_status=event.status,
    )


def join(db: Session, event_id: UUID, user_id: UUID) -> RegistrationState:
    event = lock_event(db, event_id)
    if event.status not in {"PUBLISHED", "GROUPS_PROPOSED"}:
        raise HTTPException(404, "Published event not found")
    registration = find_registration(db, event, user_id)
    # Retrying an existing successful join does not change its queue priority.
    if registration is not None and registration.status != "CANCELLED":
        return state(db, event, registration)
    now = utcnow()  # Check time after waiting for the lock, not before.
    if not event.registration_opens_at <= now < event.registration_closes_at:
        raise HTTPException(409, "Registration is not open for this event")
    registered, _ = counts(db, event)
    status: RegistrationStatus = (
        "REGISTERED" if event.capacity is None or registered < event.capacity else "WAITLISTED"
    )
    # A monotonic event-local ticket avoids clock ties and sends rejoining users to the back.
    queue_number = (
        db.scalar(
            select(func.max(Registration.queue_number)).where(Registration.event_id == event.id)
        )
        or 0
    ) + 1
    if registration is None:
        registration = Registration(event_id=event.id, user_id=user_id)
        db.add(registration)
    registration.status = status
    registration.queue_number = queue_number
    registration.registered_at = now
    event.version += 1
    db.add(AuditLog(actor_id=user_id, event_id=event.id, action=f"registration.{status.lower()}"))
    db.flush()
    return state(db, event, registration)


def withdraw(db: Session, event_id: UUID, user_id: UUID) -> RegistrationState:
    event = lock_event(db, event_id)
    if event.status == "GROUPS_FINALIZED":
        from app.models import User
        from app.services import teams

        user = db.get(User, user_id)
        assert user is not None
        teams.withdraw(db, event_id, user)
        return state(db, event, find_registration(db, event, user_id))
    registration = find_registration(db, event, user_id)
    if event.status not in {"PUBLISHED", "GROUPS_PROPOSED"} and registration is None:
        raise HTTPException(404, "Event not found")
    if registration is None or registration.status == "CANCELLED":
        return state(db, event, registration)
    if event.status not in {"PUBLISHED", "GROUPS_PROPOSED"} or utcnow() >= event.start_at:
        raise HTTPException(
            409, "Self-service withdrawal is available only before event start on an active event"
        )
    had_seat = registration.status == "REGISTERED"
    registration.status = "CANCELLED"
    if had_seat:
        oldest = db.scalar(
            select(Registration)
            .where(Registration.event_id == event.id, Registration.status == "WAITLISTED")
            .order_by(Registration.queue_number)
            .limit(1)
        )
        if oldest is not None:
            oldest.status = "REGISTERED"
    event.version += 1
    db.add(AuditLog(actor_id=user_id, event_id=event.id, action="registration.cancelled"))
    # Withdrawal and replacement commit together through the request's DB dependency.
    db.flush()
    return state(db, event, registration)
