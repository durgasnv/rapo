from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import ScalarSelect

from app.models import Event, Registration, User
from app.schemas.events import EventOut
from app.schemas.registrations import (
    MyRegistration,
    MyRegistrationPage,
    RegistrationState,
    RosterPage,
    RosterRegistration,
)
from app.security import CurrentIdentity, Db, Organizer
from app.services import registrations as service

router = APIRouter(tags=["registrations"])
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def queue_position() -> ScalarSelect[int]:
    queued = aliased(Registration)
    return (
        select(func.count())
        .select_from(queued)
        .where(
            queued.event_id == Registration.event_id,
            queued.status == "WAITLISTED",
            queued.queue_number <= Registration.queue_number,
        )
        .correlate(Registration)
        .scalar_subquery()
    )


@router.get("/events/{event_id}/registration", response_model=RegistrationState)
def my_event_registration(event_id: UUID, identity: CurrentIdentity, db: Db) -> RegistrationState:
    event = service.lock_event(db, event_id, shared=True)
    registration = service.find_registration(db, event, identity.user.id)
    if (
        event.status not in {"PUBLISHED", "GROUPS_PROPOSED", "GROUPS_FINALIZED"}
        and registration is None
    ):
        raise HTTPException(404, "Event not found")
    return service.state(db, event, registration)


@router.post("/events/{event_id}/register", response_model=RegistrationState)
def register(event_id: UUID, identity: CurrentIdentity, db: Db) -> RegistrationState:
    return service.join(db, event_id, identity.user.id)


@router.delete("/events/{event_id}/registration", response_model=RegistrationState)
def withdraw(event_id: UUID, identity: CurrentIdentity, db: Db) -> RegistrationState:
    return service.withdraw(db, event_id, identity.user.id)


@router.get("/me/registrations", response_model=MyRegistrationPage)
def my_registrations(
    identity: CurrentIdentity, db: Db, offset: Offset = 0, limit: Limit = 20
) -> MyRegistrationPage:
    condition = Registration.user_id == identity.user.id
    total = db.scalar(select(func.count()).select_from(Registration).where(condition)) or 0
    # The rows and live queue positions share a single PostgreSQL statement snapshot.
    rows = db.execute(
        select(Registration, Event, queue_position())
        .join(Event, Event.id == Registration.event_id)
        .where(condition)
        .order_by(Registration.registered_at.desc(), Registration.id)
        .offset(offset)
        .limit(limit)
    )
    return MyRegistrationPage(
        items=[
            MyRegistration(
                **service.registration_out(registration, position).model_dump(),
                event=EventOut.model_validate(event),
            )
            for registration, event, position in rows
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/events/{event_id}/registrations", response_model=RosterPage)
def event_registrations(
    event_id: UUID, organizer: Organizer, db: Db, offset: Offset = 0, limit: Limit = 20
) -> RosterPage:
    event = service.lock_event(db, event_id, shared=True)
    if event.organizer_id != organizer.id:
        raise HTTPException(404, "Event not found")
    condition = Registration.event_id == event.id
    total = db.scalar(select(func.count()).select_from(Registration).where(condition)) or 0
    registered, waiting = service.counts(db, event)
    rows = db.execute(
        select(Registration, User.name, queue_position())
        .join(User, User.id == Registration.user_id)
        .where(condition)
        .order_by(
            case(
                (Registration.status == "REGISTERED", 0),
                (Registration.status == "WAITLISTED", 1),
                else_=2,
            ),
            Registration.queue_number,
        )
        .offset(offset)
        .limit(limit)
    )
    return RosterPage(
        items=[
            RosterRegistration(
                **service.registration_out(registration, position).model_dump(),
                user_id=registration.user_id,
                name=name,
            )
            for registration, name, position in rows
        ],
        total=total,
        offset=offset,
        limit=limit,
        registered_count=registered,
        waitlisted_count=waiting,
    )
