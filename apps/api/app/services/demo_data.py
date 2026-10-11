"""Synthetic demo fixtures. The caller owns the transaction."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from app.schemas.grouping import GroupingInput
from app.schemas.teams import ConfirmationInput
from app.security import hasher
from app.services import grouping, teams
from app.services.grouping_engine import score


@dataclass(frozen=True)
class DemoResult:
    namespace: str
    scheduled_event_id: UUID
    roster_event_id: UUID
    created: bool


def identity(namespace: str, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"rapo:demo:v1:{namespace}:{key}")


def member_email(namespace: str, number: int) -> str:
    return f"demo.{namespace}.{number:03d}@example.com"


def event_fixture(
    db: Session, owner: User, namespace: str, key: str, now: datetime, *, waiting: bool = True
) -> Event:
    event = Event(
        id=identity(namespace, key),
        organizer_id=owner.id,
        title=f"[DEMO {namespace}] {key.replace('-', ' ').title()}",
        description="Synthetic demo data for testing team formation and roster management.",
        location="Demo community",
        timezone="UTC",
        start_at=now + timedelta(days=7),
        end_at=now + timedelta(days=7, hours=2),
        registration_opens_at=now - timedelta(days=7),
        registration_closes_at=now - timedelta(hours=2),
        grouping_at=now - timedelta(hours=1),
        confirmation_deadline=now + timedelta(days=5),
        capacity=100,
        min_team_size=3,
        max_team_size=5,
        status="PUBLISHED",
    )
    db.add(event)
    db.flush()
    db.add_all(
        Registration(
            event_id=event.id,
            user_id=identity(namespace, f"member-{number}"),
            status="REGISTERED" if number <= 100 else "WAITLISTED",
            queue_number=number,
            registered_at=event.registration_opens_at + timedelta(minutes=number),
        )
        for number in range(1, 121 if waiting else 101)
    )
    db.flush()
    return event


def completed_history(db: Session, owner: User, namespace: str, now: datetime, index: int) -> None:
    # Fixture construction backdates the entire schedule, including registrations.
    event = event_fixture(
        db,
        owner,
        namespace,
        f"history-{index + 1}",
        now - timedelta(days=70 - index * 14),
        waiting=False,
    )
    event.status = "COMPLETED"
    db.flush()
    _, history, fingerprint = grouping.inputs(db, event)
    people = [identity(namespace, f"member-{n}") for n in range(1, 101)]
    # Two identical rounds repeat every pairing; the third shifts groups by two people.
    if index == 2:
        people = people[2:] + people[:2]
    groups = [people[offset : offset + 4] for offset in range(0, 100, 4)]
    cost, fairness = score(groups, history)
    run = GroupingRun(
        event_id=event.id,
        request_id=identity(namespace, f"history-run-{index}"),
        created_by=owner.id,
        status="FINALIZED",
        algorithm_version="demo-history-v1",
        seed=index,
        input_hash=fingerprint,
        min_team_size=3,
        max_team_size=5,
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
    for number, group in enumerate(groups, 1):
        team = Team(
            run_id=run.id,
            number=number,
            score=score([group], history)[0],
            explanation="Synthetic historical team, manually arranged to exercise repeats.",
        )
        final = FinalTeam(event_id=event.id, run_id=run.id, number=number, target_size=4)
        db.add_all([team, final])
        db.flush()
        db.add_all(TeamMember(team_id=team.id, run_id=run.id, user_id=person) for person in group)
        db.add_all(
            Assignment(
                event_id=event.id,
                team_id=final.id,
                user_id=person,
                status="CONFIRMED",
                assigned_at=event.grouping_at,
                confirmed_at=event.confirmation_deadline,
            )
            for person in group
        )
    db.flush()


def seed(db: Session, organizer_email: str, namespace: str, password: str) -> DemoResult:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", namespace):
        raise ValueError("Namespace must be 1–32 lowercase letters, digits or hyphens.")
    owner = db.scalar(select(User).where(User.email == organizer_email.strip().lower()))
    if owner is None or owner.role != "organizer":
        raise ValueError("Use an existing account with organizer access.")
    scheduled_id, roster_id = (
        identity(namespace, "scheduled-grouping"),
        identity(namespace, "roster-repair"),
    )
    # The transaction lock prevents two CLI processes from creating the same demo twice.
    lock = int.from_bytes(identity(namespace, "lock").bytes[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    marker = db.get(AuditLog, identity(namespace, "marker"))
    if marker is not None:
        if marker.actor_id != owner.id:
            raise ValueError("This namespace belongs to another organizer. Choose a new namespace.")
        return DemoResult(namespace, scheduled_id, roster_id, False)
    if not 12 <= len(password) <= 128:
        raise ValueError("Demo password must contain 12–128 characters.")
    ids = [identity(namespace, f"member-{n}") for n in range(1, 121)]
    emails = [member_email(namespace, n) for n in range(1, 121)]
    event_ids = [scheduled_id, roster_id] + [identity(namespace, f"history-{n}") for n in (1, 2, 3)]
    if db.scalar(select(User.id).where(User.id.in_(ids) | User.email.in_(emails)).limit(1)):
        raise ValueError("Demo member identity already exists. Choose a new namespace.")
    if db.scalar(select(Event.id).where(Event.id.in_(event_ids)).limit(1)):
        raise ValueError("Demo event identity already exists. Choose a new namespace.")
    db.add_all(
        User(
            id=person,
            name=f"Demo {namespace} Member {n:03d}",
            email=email,
            password_hash=hasher.hash(password),
            role="participant",
        )
        for n, (person, email) in enumerate(zip(ids, emails, strict=True), 1)
    )
    db.flush()
    now = utcnow()
    for index in range(3):
        completed_history(db, owner, namespace, now, index)
    scheduled = event_fixture(db, owner, namespace, "scheduled-grouping", now)
    roster = event_fixture(db, owner, namespace, "roster-repair", now)
    proposal = grouping.create(
        db, roster.id, owner, GroupingInput(request_id=identity(namespace, "roster-run"), seed=42)
    )
    final = teams.finalize(db, roster.id, proposal.id, owner, roster.version)
    first, second = final.teams[:2]
    declined, withdrawn = (
        db.get(User, first.members[0].user_id),
        db.get(User, second.members[0].user_id),
    )
    assert declined is not None and withdrawn is not None
    teams.confirm(
        db,
        roster.id,
        first.id,
        declined,
        ConfirmationInput(team_version=first.version, decision="decline"),
    )
    teams.withdraw(db, roster.id, withdrawn)
    for team in final.teams[2:4]:
        for member in team.members:
            user = db.get(User, member.user_id)
            assert user is not None
            teams.confirm(
                db,
                roster.id,
                team.id,
                user,
                ConfirmationInput(team_version=team.version, decision="confirm"),
            )
    db.add(
        AuditLog(
            id=identity(namespace, "marker"),
            actor_id=owner.id,
            event_id=scheduled.id,
            action="demo.seeded",
            after_json={"namespace": namespace, "version": 1},
        )
    )
    db.flush()
    return DemoResult(namespace, scheduled.id, roster.id, True)
