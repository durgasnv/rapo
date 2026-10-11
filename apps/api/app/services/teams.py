import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AuditLog,
    Event,
    FinalTeam,
    GroupingRun,
    Registration,
    RosterAction,
    Team,
    TeamMember,
    User,
    utcnow,
)
from app.schemas.teams import (
    AssignmentOut,
    ConfirmationInput,
    DeadlineInput,
    FinalTeamOut,
    OwnerAction,
    ReassignInput,
    RosterOut,
)
from app.services.grouping import inputs, owned
from app.services.notifications import roster_change
from app.services.registrations import lock_event

ACTIVE = {"PENDING", "CONFIRMED"}


def members(db: Session, team: FinalTeam) -> list[Assignment]:
    return list(
        db.scalars(
            select(Assignment)
            .where(Assignment.team_id == team.id, Assignment.status.in_(ACTIVE))
            .order_by(Assignment.user_id)
        )
    )


def roster(db: Session, event: Event, user: User) -> RosterOut:
    owner = event.organizer_id == user.id and user.role == "organizer"
    own_assignment = db.scalar(
        select(Assignment).where(Assignment.event_id == event.id, Assignment.user_id == user.id)
    )
    if not owner and own_assignment is None:
        registered = db.scalar(
            select(Registration.id).where(
                Registration.event_id == event.id, Registration.user_id == user.id
            )
        )
        if registered is None:
            raise HTTPException(404, "Team assignment not found")
    query = select(FinalTeam).where(FinalTeam.event_id == event.id)
    if not owner:
        query = query.where(
            FinalTeam.id
            == (
                own_assignment.team_id
                if own_assignment and own_assignment.status in ACTIVE
                else None
            )
        )
    teams = list(db.scalars(query.order_by(FinalTeam.number)))
    rows = db.execute(
        select(Assignment, User.name)
        .join(User, User.id == Assignment.user_id)
        .where(Assignment.team_id.in_([t.id for t in teams]))
        .order_by(Assignment.assigned_at, Assignment.user_id)
    )
    names: dict[UUID, list[AssignmentOut]] = {t.id: [] for t in teams}
    for row, name in rows:
        if owner or row.status in ACTIVE:
            names[row.team_id].append(
                AssignmentOut(
                    user_id=row.user_id, name=name, status=row.status, confirmed_at=row.confirmed_at
                )
            )
    now = utcnow()
    result = []
    for team in teams:
        active = [m for m in names[team.id] if m.status in ACTIVE]
        reasons = []
        if not event.min_team_size <= len(active) <= event.max_team_size:
            reasons.append("Active team size is outside the event limits.")
        if len(active) < team.target_size:
            reasons.append("A vacancy needs replacement or organizer approval to continue.")
        pending = any(m.status == "PENDING" for m in active)
        if pending and now >= event.confirmation_deadline:
            reasons.append("Confirmation deadline passed with unconfirmed members.")
        result.append(
            FinalTeamOut(
                id=team.id,
                number=team.number,
                version=team.version,
                target_size=team.target_size,
                status="NEEDS_ATTENTION"
                if reasons
                else "AWAITING_CONFIRMATIONS"
                if pending
                else "READY",
                reasons=reasons,
                members=names[team.id],
            )
        )
    return RosterOut(
        event_id=event.id,
        event_status=event.status,
        version=event.version,
        confirmation_deadline=event.confirmation_deadline,
        confirmation_open=event.status == "GROUPS_FINALIZED" and now < event.confirmation_deadline,
        withdrawal_open=event.status == "GROUPS_FINALIZED" and now < event.start_at,
        own_status=own_assignment.status if own_assignment else None,
        teams=result,
    )


def snapshot(db: Session, event: Event) -> dict[str, object]:
    db.flush()
    assignments = db.scalars(
        select(Assignment).where(Assignment.event_id == event.id).order_by(Assignment.user_id)
    )
    return {
        "teams": [
            {"id": str(t.id), "target_size": t.target_size, "version": t.version}
            for t in db.scalars(
                select(FinalTeam).where(FinalTeam.event_id == event.id).order_by(FinalTeam.number)
            )
        ],
        "version": event.version,
        "deadline": event.confirmation_deadline.isoformat(),
        "members": [
            {"user_id": str(m.user_id), "team_id": str(m.team_id), "status": m.status}
            for m in assignments
        ],
    }


def record(db: Session, event: Event, actor: User, action: str, before: dict[str, object]) -> None:
    event.version += 1
    db.add(
        AuditLog(
            actor_id=actor.id,
            event_id=event.id,
            action=action,
            before_json=before,
            after_json=snapshot(db, event),
        )
    )
    db.flush()
    roster_change(db, event, action, before)


def writable(event: Event, *, confirmation: bool = False) -> None:
    if event.status != "GROUPS_FINALIZED" or utcnow() >= event.start_at:
        raise HTTPException(409, "Roster changes require a finalized event before it starts.")
    if confirmation and utcnow() >= event.confirmation_deadline:
        raise HTTPException(409, "Confirmation deadline passed. Ask the organizer to extend it.")


def reset(db: Session, team: FinalTeam) -> None:
    team.version += 1
    for member in members(db, team):
        member.status, member.confirmed_at = "PENDING", None


def final_team(db: Session, event: Event, team_id: UUID) -> FinalTeam:
    team = db.get(FinalTeam, team_id)
    if team is None or team.event_id != event.id:
        raise HTTPException(404, "Team not found")
    return team


def finalize(db: Session, event_id: UUID, run_id: UUID, owner: User, version: int) -> RosterOut:
    event = owned(db, event_id, owner)
    run = db.get(GroupingRun, run_id)
    if run is None or run.event_id != event.id:
        raise HTTPException(404, "Grouping preview not found")
    if run.status == "FINALIZED":
        return roster(db, event, owner)
    if event.status != "GROUPS_PROPOSED":
        raise HTTPException(409, "Only an unfinalized grouping preview can be finalized.")
    if event.version != version:
        raise HTTPException(409, "This event changed. Refresh before finalizing.")
    if utcnow() >= event.confirmation_deadline:
        raise HTTPException(409, "Finalize before the confirmation deadline.")
    participants, _, fingerprint = inputs(db, event)
    if run.input_hash != fingerprint:
        raise HTTPException(409, "This preview is stale. Regenerate before finalizing.")
    teams = list(db.scalars(select(Team).where(Team.run_id == run.id).order_by(Team.number)))
    assignments = list(db.scalars(select(TeamMember).where(TeamMember.run_id == run.id)))
    proposed = [m.user_id for m in assignments]
    if (
        not participants
        or sorted(proposed) != sorted(participants)
        or len(set(proposed)) != len(proposed)
    ):
        raise HTTPException(
            409, "Preview must cover every eligible person exactly once. Regenerate."
        )
    if event.capacity is not None and len(participants) > event.capacity:
        raise HTTPException(409, "Eligible count exceeds event capacity.")
    before = snapshot(db, event)
    for team in teams:
        ids = [m.user_id for m in assignments if m.team_id == team.id]
        if not event.min_team_size <= len(ids) <= event.max_team_size:
            raise HTTPException(409, "A proposed team violates size limits. Regenerate.")
        final = FinalTeam(
            event_id=event.id, run_id=run.id, number=team.number, target_size=len(ids)
        )
        db.add(final)
        db.flush()
        db.add_all([Assignment(event_id=event.id, team_id=final.id, user_id=p) for p in ids])
    run.status, event.status = "FINALIZED", "GROUPS_FINALIZED"
    record(db, event, owner, "teams.finalized", before)
    return roster(db, event, owner)


def confirm(
    db: Session, event_id: UUID, team_id: UUID, user: User, body: ConfirmationInput
) -> RosterOut:
    event = lock_event(db, event_id)
    team = final_team(db, event, team_id)
    member = db.scalar(
        select(Assignment).where(Assignment.event_id == event.id, Assignment.user_id == user.id)
    )
    if member is None or member.team_id != team.id:
        raise HTTPException(404, "Team assignment not found")
    desired = "CONFIRMED" if body.decision == "confirm" else "DECLINED"
    if member.status == desired and (desired == "DECLINED" or body.team_version == team.version):
        return roster(db, event, user)
    writable(event, confirmation=True)
    if member.status not in ACTIVE:
        raise HTTPException(409, "This assignment is no longer active.")
    if team.version != body.team_version:
        raise HTTPException(409, "Your teammates changed. Refresh before confirming.")
    if body.decision == "decline":
        return withdraw(db, event.id, user, decline=True)
    before = snapshot(db, event)
    member.status, member.confirmed_at = "CONFIRMED", utcnow()
    record(db, event, user, "team.confirmed", before)
    return roster(db, event, user)


def withdraw(db: Session, event_id: UUID, user: User, *, decline: bool = False) -> RosterOut:
    event = lock_event(db, event_id)
    member = db.scalar(
        select(Assignment).where(Assignment.event_id == event.id, Assignment.user_id == user.id)
    )
    registration = db.scalar(
        select(Registration).where(
            Registration.event_id == event.id, Registration.user_id == user.id
        )
    )
    if registration is None:
        raise HTTPException(404, "Registration not found")
    if registration.status == "CANCELLED":
        return roster(db, event, user)
    writable(event, confirmation=decline)
    before = snapshot(db, event)
    registration.status = "CANCELLED"
    if member is not None and member.status in ACTIVE:
        member.status = "DECLINED" if decline else "WITHDRAWN"
        member.confirmed_at = None
        db.flush()
        reset(db, final_team(db, event, member.team_id))
    record(db, event, user, "team.declined" if decline else "team.withdrawn", before)
    return roster(db, event, user)


def action_start(db: Session, event: Event, body: OwnerAction, action: str) -> tuple[str, bool]:
    fingerprint = hashlib.sha256(
        json.dumps(
            {"action": action, "body": body.model_dump(mode="json")}, sort_keys=True
        ).encode()
    ).hexdigest()
    prior = db.scalar(
        select(RosterAction).where(
            RosterAction.event_id == event.id, RosterAction.request_id == body.request_id
        )
    )
    if prior is not None:
        if prior.payload_hash != fingerprint:
            raise HTTPException(409, "Request ID already used for a different roster change.")
        return fingerprint, True
    if event.version != body.version:
        raise HTTPException(409, "This roster changed. Refresh before saving.")
    writable(event)
    return fingerprint, False


def action_finish(db: Session, event: Event, body: OwnerAction, fingerprint: str) -> None:
    db.add(RosterAction(event_id=event.id, request_id=body.request_id, payload_hash=fingerprint))
    db.flush()


def repair(
    db: Session, event_id: UUID, team_id: UUID, owner: User, body: OwnerAction, action: str
) -> RosterOut:
    event = owned(db, event_id, owner)
    team = final_team(db, event, team_id)
    fingerprint, retry = action_start(db, event, body, f"{action}:{team.id}")
    if retry:
        return roster(db, event, owner)
    before = snapshot(db, event)
    count = len(members(db, team))
    if action == "replace":
        writable(event, confirmation=True)
        if count >= team.target_size or count >= event.max_team_size:
            raise HTTPException(409, "This team has no vacancy.")
        waiting = db.scalar(
            select(Registration)
            .where(
                Registration.event_id == event.id,
                Registration.status == "WAITLISTED",
                ~select(Assignment.id)
                .where(
                    Assignment.event_id == event.id,
                    Assignment.user_id == Registration.user_id,
                )
                .exists(),
            )
            .order_by(Registration.queue_number)
            .limit(1)
        )
        if waiting is None:
            raise HTTPException(409, "No eligible waitlisted participant is available.")
        waiting.status = "REGISTERED"
        db.add(Assignment(event_id=event.id, team_id=team.id, user_id=waiting.user_id))
        db.flush()
        reset(db, team)
    elif action == "continue":
        if not event.min_team_size <= count <= event.max_team_size:
            raise HTTPException(409, "Cannot approve a team outside the size limits.")
        team.target_size = count
    else:
        raise ValueError("Unknown repair action")
    record(db, event, owner, f"team.{action}", before)
    action_finish(db, event, body, fingerprint)
    return roster(db, event, owner)


def extend_deadline(db: Session, event_id: UUID, owner: User, body: DeadlineInput) -> RosterOut:
    event = owned(db, event_id, owner)
    fingerprint, retry = action_start(db, event, body, "deadline")
    if retry:
        return roster(db, event, owner)
    if (
        not max(utcnow(), event.confirmation_deadline)
        < body.confirmation_deadline
        <= event.start_at
    ):
        raise HTTPException(422, "Extend the deadline into the future, no later than event start.")
    before = snapshot(db, event)
    event.confirmation_deadline = body.confirmation_deadline
    record(db, event, owner, "teams.deadline_extended", before)
    action_finish(db, event, body, fingerprint)
    return roster(db, event, owner)


def reassign(db: Session, event_id: UUID, owner: User, body: ReassignInput) -> RosterOut:
    event = owned(db, event_id, owner)
    fingerprint, retry = action_start(db, event, body, "reassign")
    if retry:
        return roster(db, event, owner)
    writable(event, confirmation=True)
    member = db.scalar(
        select(Assignment).where(
            Assignment.event_id == event.id,
            Assignment.user_id == body.user_id,
            Assignment.status.in_(ACTIVE),
        )
    )
    if member is None:
        raise HTTPException(404, "Active assignment not found")
    source, target = (
        final_team(db, event, member.team_id),
        final_team(db, event, body.target_team_id),
    )
    if source.id == target.id:
        raise HTTPException(409, "Choose a different target team.")
    swap = None
    if body.swap_user_id is not None:
        swap = db.scalar(
            select(Assignment).where(
                Assignment.event_id == event.id,
                Assignment.user_id == body.swap_user_id,
                Assignment.team_id == target.id,
                Assignment.status.in_(ACTIVE),
            )
        )
        if swap is None:
            raise HTTPException(404, "Swap participant is not active in the target team")
    a, b = len(members(db, source)), len(members(db, target))
    if swap is None:
        a, b = a - 1, b + 1
    if not all(event.min_team_size <= n <= event.max_team_size for n in (a, b)):
        raise HTTPException(409, "Both teams must remain within the event's size limits.")
    before = snapshot(db, event)
    member.team_id = target.id
    if swap is not None:
        swap.team_id = source.id
    db.flush()
    source.target_size, target.target_size = a, b
    reset(db, source)
    reset(db, target)
    record(db, event, owner, "teams.reassigned", before)
    action_finish(db, event, body, fingerprint)
    return roster(db, event, owner)
