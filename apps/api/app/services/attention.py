from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Assignment, Event, FinalTeam, GroupingJob, User, utcnow
from app.schemas.attention import AttentionEvent, AttentionPage
from app.services.teams import ACTIVE


def overview(db: Session, owner: User, offset: int, limit: int) -> AttentionPage:
    now = utcnow()
    # Aggregate memberships once, scoped to this owner's finalized events. Empty teams
    # must survive the outer join so their vacancies and minimum-size issues count.
    teams = (
        select(
            FinalTeam.event_id,
            FinalTeam.id,
            FinalTeam.target_size,
            Event.min_team_size,
            Event.max_team_size,
            Event.confirmation_deadline,
            func.count(Assignment.id).filter(Assignment.status.in_(ACTIVE)).label("active"),
            func.count(Assignment.id).filter(Assignment.status == "PENDING").label("pending"),
        )
        .join(Event, Event.id == FinalTeam.event_id)
        .outerjoin(Assignment, Assignment.team_id == FinalTeam.id)
        .where(Event.organizer_id == owner.id, Event.status == "GROUPS_FINALIZED")
        .group_by(FinalTeam.id, Event.id)
        .subquery()
    )
    issues = (
        select(
            teams.c.event_id,
            func.count().filter(teams.c.active < teams.c.min_team_size).label("below"),
            func.count().filter(teams.c.active > teams.c.max_team_size).label("above"),
            func.sum(
                case(
                    (teams.c.active < teams.c.target_size, teams.c.target_size - teams.c.active),
                    else_=0,
                )
            ).label("vacancies"),
            func.sum(case((teams.c.confirmation_deadline <= now, teams.c.pending), else_=0)).label(
                "overdue"
            ),
        )
        .group_by(teams.c.event_id)
        .subquery()
    )
    query = (
        select(
            Event,
            issues.c.below,
            issues.c.above,
            issues.c.vacancies,
            issues.c.overdue,
            GroupingJob.status,
        )
        .outerjoin(issues, issues.c.event_id == Event.id)
        .outerjoin(GroupingJob, GroupingJob.event_id == Event.id)
        .where(
            Event.organizer_id == owner.id,
            or_(
                Event.status == "GROUPS_PROPOSED",
                and_(Event.status == "PUBLISHED", GroupingJob.status.in_(["FAILED", "BLOCKED"])),
                and_(
                    Event.status == "GROUPS_FINALIZED",
                    or_(
                        issues.c.below > 0,
                        issues.c.above > 0,
                        issues.c.vacancies > 0,
                        issues.c.overdue > 0,
                    ),
                ),
            ),
        )
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(Event.start_at, Event.id).offset(offset).limit(limit))
    items = []
    for event, below, above, vacancies, overdue, job_status in rows:
        reasons = []
        if event.status == "GROUPS_PROPOSED":
            reasons.append("Preview awaiting review.")
        elif event.status == "PUBLISHED":
            reasons.append(
                "Grouping failed. Review the job details."
                if job_status == "FAILED"
                else "Grouping blocked. Review feasibility and job details."
            )
        else:
            if below:
                reasons.append(f"Below minimum: {below} {'team' if below == 1 else 'teams'}.")
            if above:
                reasons.append(f"Above maximum: {above} {'team' if above == 1 else 'teams'}.")
            if vacancies:
                reasons.append(
                    f"Vacancy: {vacancies} unfilled {'place' if vacancies == 1 else 'places'}."
                )
            if overdue:
                reasons.append(
                    f"Confirmation overdue: {overdue} {'member' if overdue == 1 else 'members'}."
                )
        items.append(
            AttentionEvent(
                event_id=event.id,
                title=event.title,
                start_at=event.start_at,
                timezone=event.timezone,
                status=event.status,
                reasons=reasons,
            )
        )
    return AttentionPage(items=items, total=total, offset=offset, limit=limit)
