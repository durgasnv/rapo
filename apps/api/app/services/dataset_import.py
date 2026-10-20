"""Transactional, isolated fixture imports. The caller owns commit/rollback."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AuditLog,
    Event,
    FinalTeam,
    GroupingRun,
    Registration,
    Team,
    TeamMember,
    User,
    utcnow,
)
from app.schemas.dataset import Dataset, DatasetTeam
from app.schemas.events import EventInput
from app.security import hasher
from app.services import grouping
from app.services.grouping_engine import score

DATES = (
    "start_at",
    "end_at",
    "registration_opens_at",
    "registration_closes_at",
    "grouping_at",
    "confirmation_deadline",
)


@dataclass(frozen=True)
class ImportResult:
    event_ids: dict[str, UUID]
    participants: int
    cancelled_registrations: int
    created: bool


def identity(namespace: str, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"rapo:dataset:v1:{namespace}:{key}")


def member_email(namespace: str, source_id: int) -> str:
    return f"demo.{namespace}.{source_id:03d}@example.com"


def import_dataset(
    db: Session,
    dataset: Dataset,
    organizer_email: str,
    namespace: str,
    password: str,
    *,
    shift_days: int = 0,
) -> ImportResult:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", namespace):
        raise ValueError("Namespace must be 1–32 lowercase letters, digits or hyphens")
    if not -3650 <= shift_days <= 3650:
        raise ValueError("Schedule shift must be within 3650 days")
    owner = db.scalar(select(User).where(User.email == organizer_email.strip().lower()))
    if owner is None or owner.role != "organizer":
        raise ValueError("Use an existing account with organizer access")
    lock = int.from_bytes(identity(namespace, "lock").bytes[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    fingerprint = hashlib.sha256(dataset.model_dump_json().encode()).hexdigest()
    participants = [m for m in dataset.members if m.role == "participant"]
    event_ids = {e.id: identity(namespace, f"event:{e.id}") for e in dataset.events}
    cancelled = sum(a.status in {"DECLINED", "WITHDRAWN"} for a in dataset.assignments)
    result = ImportResult(event_ids, len(participants), cancelled, False)
    marker = db.get(AuditLog, identity(namespace, "marker"))
    if marker is not None:
        metadata = marker.after_json or {}
        if marker.actor_id != owner.id:
            raise ValueError("This namespace belongs to another organizer")
        if metadata.get("fingerprint") != fingerprint or metadata.get("shift_days") != shift_days:
            raise ValueError("This namespace contains different source data; choose a new name")
        return result
    if not 12 <= len(password) <= 128:
        raise ValueError("Demo password must contain 12–128 characters")
    member_ids = {m.id: identity(namespace, f"member:{m.id}") for m in participants}
    emails = [member_email(namespace, m.id) for m in participants]
    if db.scalar(select(User.id).where(User.id.in_(member_ids.values()) | User.email.in_(emails))):
        raise ValueError("Demo member identity already exists; choose a new namespace")
    if db.scalar(select(Event.id).where(Event.id.in_(event_ids.values()))):
        raise ValueError("Demo event identity already exists; choose a new namespace")
    events = {}
    for source in dataset.events:
        body = {key: getattr(source, key) for key in EventInput.model_fields}
        for key in DATES:
            body[key] += timedelta(days=shift_days)
        body["title"] = f"[DEMO {namespace}] {source.title}"
        validated = EventInput.model_validate(body)
        if source.status == "COMPLETED" and validated.end_at > utcnow():
            raise ValueError("A schedule shift cannot move completed history into the future")
        events[source.id] = Event(
            **validated.model_dump(),
            id=event_ids[source.id],
            organizer_id=owner.id,
            status=source.status,
            version=source.version,
        )
    db.add_all(
        User(
            id=member_ids[m.id],
            name=m.name,
            email=member_email(namespace, m.id),
            password_hash=hasher.hash(password),
            role="participant",
        )
        for m in participants
    )
    db.add_all(events.values())
    db.flush()
    registrations = {}
    for row in dataset.registrations:
        event = events[row.event_id]
        maximum = max(r.queue_number for r in dataset.registrations if r.event_id == row.event_id)
        registered_at = event.registration_opens_at + (
            event.registration_closes_at - event.registration_opens_at
        ) * (row.queue_number / (maximum + 1))
        registration = Registration(
            event_id=event.id,
            user_id=member_ids[row.member_id],
            status=row.status,
            queue_number=row.queue_number,
            registered_at=registered_at,
        )
        registrations[row.event_id, row.member_id] = registration
        db.add(registration)
    db.flush()
    sources = {h.event_id: (h.teams, 0) for h in dataset.completed_event_history}
    sources.update({r.event_id: (r.teams, r.seed) for r in dataset.grouping_runs})
    assignments = {(a.event_id, a.member_id): a.status for a in dataset.assignments}
    for key in sorted(sources, key=lambda key: events[key].end_at):
        teams, seed = sources[key]
        persist_grouping(db, events[key], teams, seed, member_ids, assignments, key, namespace)
    for assignment in dataset.assignments:
        if assignment.status in {"DECLINED", "WITHDRAWN"}:
            registrations[assignment.event_id, assignment.member_id].status = "CANCELLED"
    for index, (key, event) in enumerate(events.items()):
        db.add(
            AuditLog(
                id=identity(namespace, "marker" if index == 0 else f"audit:{key}"),
                actor_id=owner.id,
                event_id=event.id,
                action="demo.seeded",
                after_json={
                    "dataset": "college",
                    "namespace": namespace,
                    "fingerprint": fingerprint,
                    "shift_days": shift_days,
                    "cancelled_registrations": cancelled,
                },
            )
        )
    db.flush()
    return ImportResult(event_ids, len(participants), cancelled, True)


def persist_grouping(
    db: Session,
    event: Event,
    teams: list[DatasetTeam],
    seed: int,
    member_ids: dict[int, UUID],
    assignments: Mapping[tuple[str, int], str],
    source_id: str,
    namespace: str,
) -> None:
    _, history, fingerprint = grouping.inputs(db, event)
    groups = [[member_ids[person] for person in team.members] for team in teams]
    cost, fairness = score(groups, history)
    run = GroupingRun(
        event_id=event.id,
        request_id=identity(namespace, f"run:{source_id}"),
        created_by=event.organizer_id,
        status="FINALIZED",
        algorithm_version="dataset-import-v1",
        seed=seed,
        min_team_size=event.min_team_size,
        max_team_size=event.max_team_size,
        input_hash=fingerprint,
        score=cost,
        fairness=fairness,
        baseline_score=cost,
        baseline_fairness=fairness,
        evaluations=0,
        history_snapshot=grouping.history_json(history),
        created_at=event.grouping_at,
    )
    db.add(run)
    db.flush()
    for source, people in zip(teams, groups, strict=True):
        team_cost = score([people], history)[0]
        preview = Team(
            run_id=run.id,
            number=source.number,
            score=team_cost,
            explanation=f"Imported college fixture. Historical pair-frequency score: {team_cost}. "
            "Source membership preserved; this was not an optimization run.",
        )
        final = FinalTeam(
            event_id=event.id, run_id=run.id, number=source.number, target_size=len(people)
        )
        db.add_all([preview, final])
        db.flush()
        for person, user_id in zip(source.members, people, strict=True):
            status = assignments.get((source_id, person), "CONFIRMED")
            db.add(TeamMember(team_id=preview.id, run_id=run.id, user_id=user_id))
            db.add(
                Assignment(
                    event_id=event.id,
                    team_id=final.id,
                    user_id=user_id,
                    status=status,
                    assigned_at=event.grouping_at,
                    confirmed_at=event.grouping_at if status == "CONFIRMED" else None,
                )
            )
    db.flush()
