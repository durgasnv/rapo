from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models import AuditLog, Event, User, utcnow
from app.schemas.events import EventInput, EventOut, EventPage, EventPatch, VersionInput
from app.security import Db, Organizer

router = APIRouter(tags=["events"])


def owned_event(event_id: UUID, organizer: User, db: Db) -> Event:
    # Serialize edits and transitions; version checks reject stale browser forms.
    event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if event is None or event.organizer_id != organizer.id:
        raise HTTPException(404, "Event not found")
    return event


def check_version(event: Event, version: int) -> None:
    if event.version != version:
        raise HTTPException(409, "This event changed. Refresh before saving.")


def record_action(db: Db, event: Event, organizer: User, action: str) -> None:
    db.add(AuditLog(actor_id=organizer.id, event_id=event.id, action=action))


@router.get("/events", response_model=EventPage)
def list_events(
    db: Db,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Literal["PUBLISHED"] = "PUBLISHED",
    date_from: date | None = None,
    date_to: date | None = None,
) -> EventPage:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Start date must not be after end date")
    query = select(Event).where(Event.status == status)
    if date_from:
        query = query.where(Event.start_at >= datetime.combine(date_from, time.min, UTC))
    if date_to:
        query = query.where(
            Event.start_at < datetime.combine(date_to + timedelta(days=1), time.min, UTC)
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    events = db.scalars(query.order_by(Event.start_at, Event.id).offset(offset).limit(limit)).all()
    return EventPage(
        items=[EventOut.model_validate(item) for item in events],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/organizer/events", response_model=list[EventOut])
def my_events(organizer: Organizer, db: Db) -> list[EventOut]:
    events = db.scalars(
        select(Event)
        .where(Event.organizer_id == organizer.id)
        .order_by(Event.created_at.desc())
        .limit(100)
    ).all()
    return [EventOut.model_validate(event) for event in events]


@router.get("/organizer/events/{event_id}", response_model=EventOut)
def get_owned_event(event_id: UUID, organizer: Organizer, db: Db) -> EventOut:
    event = db.get(Event, event_id)
    if event is None or event.organizer_id != organizer.id:
        raise HTTPException(404, "Event not found")
    return EventOut.model_validate(event)


@router.get("/events/{event_id}", response_model=EventOut)
def get_public_event(event_id: UUID, db: Db) -> EventOut:
    event = db.get(Event, event_id)
    if event is None or event.status != "PUBLISHED":
        raise HTTPException(404, "Event not found")
    return EventOut.model_validate(event)


@router.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventInput, organizer: Organizer, db: Db) -> EventOut:
    event = Event(**body.model_dump(), organizer_id=organizer.id)
    db.add(event)
    db.flush()
    record_action(db, event, organizer, "event.created")
    return EventOut.model_validate(event)


@router.patch("/events/{event_id}", response_model=EventOut)
def edit_event(event_id: UUID, body: EventPatch, organizer: Organizer, db: Db) -> EventOut:
    event = owned_event(event_id, organizer, db)
    check_version(event, body.version)
    if event.status != "DRAFT":
        raise HTTPException(409, "Only draft events can be edited in this release")
    updates = body.model_dump(exclude_unset=True, exclude={"version"})
    if {"start_at", "registration_closes_at"} & updates.keys() and "grouping_at" not in updates:
        updates["grouping_at"] = None
    data = EventInput.model_validate(event).model_dump() | updates
    try:
        validated = EventInput.model_validate(data)
    except ValidationError as error:
        # Return readable messages without serializing exception objects or private request data.
        raise HTTPException(422, "; ".join(item["msg"] for item in error.errors())) from error
    for field, value in validated.model_dump().items():
        setattr(event, field, value)
    event.version += 1
    db.flush()
    record_action(db, event, organizer, "event.updated")
    return EventOut.model_validate(event)


@router.post("/events/{event_id}/publish", response_model=EventOut)
def publish_event(event_id: UUID, body: VersionInput, organizer: Organizer, db: Db) -> EventOut:
    event = owned_event(event_id, organizer, db)
    check_version(event, body.version)
    if event.status != "DRAFT":
        raise HTTPException(409, "Only drafts can be published")
    if event.registration_closes_at <= utcnow():
        raise HTTPException(422, "Registration must close in the future before publishing")
    EventInput.model_validate(event)
    event.status = "PUBLISHED"
    event.version += 1
    record_action(db, event, organizer, "event.published")
    db.flush()
    return EventOut.model_validate(event)


@router.post("/events/{event_id}/cancel", response_model=EventOut)
def cancel_event(event_id: UUID, body: VersionInput, organizer: Organizer, db: Db) -> EventOut:
    event = owned_event(event_id, organizer, db)
    check_version(event, body.version)
    if event.status not in {"DRAFT", "PUBLISHED"}:
        raise HTTPException(409, "This event cannot be cancelled")
    event.status = "CANCELLED"
    event.version += 1
    record_action(db, event, organizer, "event.cancelled")
    db.flush()
    return EventOut.model_validate(event)
