import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

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
from app.schemas.grouping import GroupingInput, GroupingOut, MemberOut, TeamOut
from app.services.grouping_engine import ALGORITHM_VERSION, Pair, generate, score, team_sizes
from app.services.registrations import lock_event

ACTIVE_STATUSES = {"PUBLISHED", "GROUPS_PROPOSED"}


def owned(db: Session, event_id: UUID, organizer: User, *, shared: bool = False) -> Event:
    event = lock_event(db, event_id, shared=shared)
    if event.organizer_id != organizer.id:
        raise HTTPException(404, "Event not found")
    return event


def inputs(db: Session, event: Event) -> tuple[list[UUID], dict[Pair, int], str]:
    participants = list(
        db.scalars(
            select(Registration.user_id)
            .where(Registration.event_id == event.id, Registration.status == "REGISTERED")
            .order_by(Registration.user_id)
        )
    )
    first, second = aliased(TeamMember), aliased(TeamMember)
    # Count each completed event once, regardless of proposals or duplicate source rows.
    rows = db.execute(
        select(first.user_id, second.user_id, func.count(func.distinct(Event.id)))
        .select_from(first)
        .join(second, (first.team_id == second.team_id) & (first.user_id < second.user_id))
        .join(GroupingRun, GroupingRun.id == first.run_id)
        .join(Event, Event.id == GroupingRun.event_id)
        .where(
            first.user_id.in_(participants),
            second.user_id.in_(participants),
            GroupingRun.status == "FINALIZED",
            Event.status == "COMPLETED",
            Event.id != event.id,
            Event.end_at <= utcnow(),
            Event.end_at <= event.start_at,
            ~select(FinalTeam.id).where(FinalTeam.event_id == Event.id).exists(),
        )
        .group_by(first.user_id, second.user_id)
    )
    history = {(a, b): count for a, b, count in rows}
    a, b = aliased(Assignment), aliased(Assignment)
    final_rows = db.execute(
        select(a.user_id, b.user_id, func.count(func.distinct(Event.id)))
        .select_from(a)
        .join(b, (a.team_id == b.team_id) & (a.user_id < b.user_id))
        .join(FinalTeam, FinalTeam.id == a.team_id)
        .join(GroupingRun, GroupingRun.id == FinalTeam.run_id)
        .join(Event, Event.id == a.event_id)
        .where(
            a.user_id.in_(participants),
            b.user_id.in_(participants),
            a.status.in_(["PENDING", "CONFIRMED"]),
            b.status.in_(["PENDING", "CONFIRMED"]),
            GroupingRun.status == "FINALIZED",
            Event.status == "COMPLETED",
            Event.id != event.id,
            Event.end_at <= utcnow(),
            Event.end_at <= event.start_at,
        )
        .group_by(a.user_id, b.user_id)
    )
    for a_id, b_id, count in final_rows:
        history[a_id, b_id] = history.get((a_id, b_id), 0) + count
    snapshot = {
        "participants": [str(person) for person in participants],
        "sizes": [event.min_team_size, event.max_team_size],
        "history": history_json(history),
    }
    fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return participants, history, fingerprint


def history_json(history: dict[Pair, int]) -> list[list[str | int]]:
    return [[str(a), str(b), count] for (a, b), count in sorted(history.items())]


def output(db: Session, event: Event, run: GroupingRun, fingerprint: str) -> GroupingOut:
    reason = None
    if run.status == "FINALIZED":
        reason = None
    elif event.status not in ACTIVE_STATUSES:
        reason = "This event is no longer available for grouping."
    elif utcnow() >= event.start_at:
        reason = "This event has already started."
    elif run.input_hash != fingerprint:
        reason = (
            "Participants, team-size limits, or completed collaboration history changed. "
            "Regenerate."
        )
    teams = list(db.scalars(select(Team).where(Team.run_id == run.id).order_by(Team.number)))
    members: dict[UUID, list[MemberOut]] = {team.id: [] for team in teams}
    for member, name in db.execute(
        select(TeamMember, User.name)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.run_id == run.id)
        .order_by(TeamMember.user_id)
    ):
        members[member.team_id].append(MemberOut(user_id=member.user_id, name=name))
    return GroupingOut(
        id=run.id,
        event_id=event.id,
        status=run.status,
        seed=run.seed,
        algorithm_version=run.algorithm_version,
        score=run.score,
        fairness=run.fairness,
        baseline_score=run.baseline_score,
        baseline_fairness=run.baseline_fairness,
        evaluations=run.evaluations,
        created_at=run.created_at,
        stale=reason is not None,
        stale_reason=reason,
        teams=[
            TeamOut(
                number=t.number, members=members[t.id], score=t.score, explanation=t.explanation
            )
            for t in teams
        ],
    )


def create(db: Session, event_id: UUID, organizer: User, body: GroupingInput) -> GroupingOut:
    # Serialize against registrations, cancellation and other grouping requests.
    event = owned(db, event_id, organizer)
    existing = db.scalar(
        select(GroupingRun).where(
            GroupingRun.event_id == event.id, GroupingRun.request_id == body.request_id
        )
    )
    if existing is not None:
        if existing.seed != body.seed:
            raise HTTPException(409, "This request ID was already used with a different seed.")
        return output(db, event, existing, inputs(db, event)[2])
    now = utcnow()
    if event.status not in ACTIVE_STATUSES:
        raise HTTPException(409, "Only active published events can generate a preview.")
    if now < event.registration_closes_at:
        raise HTTPException(409, "Wait until registration closes before generating teams.")
    if now >= event.start_at:
        raise HTTPException(409, "Cannot generate teams after the event starts.")
    # Validate the count before fetching history, keeping over-limit requests cheap.
    count = (
        db.scalar(
            select(func.count())
            .select_from(Registration)
            .where(Registration.event_id == event.id, Registration.status == "REGISTERED")
        )
        or 0
    )
    team_sizes(count, event.min_team_size, event.max_team_size)
    participants, history, fingerprint = inputs(db, event)
    proposal = generate(participants, event.min_team_size, event.max_team_size, history, body.seed)
    run = GroupingRun(
        event_id=event.id,
        request_id=body.request_id,
        created_by=organizer.id,
        algorithm_version=ALGORITHM_VERSION,
        seed=body.seed,
        input_hash=fingerprint,
        min_team_size=event.min_team_size,
        max_team_size=event.max_team_size,
        score=proposal.score,
        fairness=proposal.fairness,
        baseline_score=proposal.baseline_score,
        baseline_fairness=proposal.baseline_fairness,
        evaluations=proposal.evaluations,
        history_snapshot=history_json(history),
    )
    db.add(run)
    db.flush()
    for number, people in enumerate(proposal.teams, 1):
        cost, _ = score([people], history)
        explanation = (
            "No previous collaborations within this proposed team."
            if cost == 0
            else f"Weighted repeat score: {cost}. Lower-frequency partnerships were preferred; "
            "this heuristic does not prove that these repeats are unavoidable."
        )
        team = Team(run_id=run.id, number=number, score=cost, explanation=explanation)
        db.add(team)
        db.flush()
        db.add_all([TeamMember(team_id=team.id, run_id=run.id, user_id=p) for p in people])
    event.status = "GROUPS_PROPOSED"
    event.version += 1
    db.add(AuditLog(actor_id=organizer.id, event_id=event.id, action="grouping.proposed"))
    db.flush()
    return output(db, event, run, fingerprint)


def read(db: Session, event_id: UUID, organizer: User, run_id: UUID | None) -> GroupingOut | None:
    event = owned(db, event_id, organizer, shared=True)
    query = select(GroupingRun).where(GroupingRun.event_id == event.id)
    if run_id is not None:
        query = query.where(GroupingRun.id == run_id)
    elif event.status in {"GROUPS_FINALIZED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}:
        # Preserve the approved preview after completion/cancellation, while
        # retaining proposals for events cancelled before any finalization.
        query = query.order_by((GroupingRun.status == "FINALIZED").desc())
    run = db.scalar(query.order_by(GroupingRun.created_at.desc(), GroupingRun.id.desc()).limit(1))
    if run is None:
        if run_id is not None:
            raise HTTPException(404, "Grouping preview not found")
        return None
    return output(db, event, run, inputs(db, event)[2])
