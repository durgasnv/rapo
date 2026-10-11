from collections import Counter
from unittest.mock import patch
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assignment, AuditLog, Event, Registration, User
from app.schemas.grouping import GroupingInput
from app.schemas.teams import OwnerAction
from app.security import verify_password
from app.services import grouping, teams
from app.services.demo_data import identity, member_email, seed

pytestmark = pytest.mark.database
PASSWORD = "Synthetic-demo-password!"


@pytest.fixture
def owner(db: Session) -> User:
    user = User(
        name="Demo owner", email="demo-owner@example.com", password_hash="unused", role="organizer"
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture(autouse=True)
def fast_demo_hashes():
    # Production keeps default Argon2 settings; lower costs keep fixture tests inexpensive.
    with patch("app.services.demo_data.hasher", PasswordHasher(time_cost=1, memory_cost=1024)):
        yield


def test_large_demo_grouping_and_roster_repair(db: Session, owner: User) -> None:
    result = seed(db, owner.email, "integration", PASSWORD)
    assert result.created
    assert db.scalar(select(func.count()).select_from(User)) == 121
    assert db.scalar(select(func.count()).select_from(Event)) == 5
    scheduled = db.get(Event, result.scheduled_event_id)
    assert scheduled is not None and scheduled.status == "PUBLISHED"
    rows = list(
        db.scalars(
            select(Registration)
            .where(Registration.event_id == scheduled.id)
            .order_by(Registration.queue_number)
        )
    )
    assert Counter(row.status for row in rows) == {"REGISTERED": 100, "WAITLISTED": 20}
    assert [row.queue_number for row in rows] == list(range(1, 121))
    for registration, historical in db.execute(
        select(Registration, Event)
        .join(Event, Event.id == Registration.event_id)
        .where(Event.status == "COMPLETED")
    ):
        assert (
            historical.registration_opens_at
            <= registration.registered_at
            < historical.registration_closes_at
        )
    people, history, _ = grouping.inputs(db, scheduled)
    assert len(people) == 100 and set(history.values()) == {1, 2, 3}
    proposal = grouping.create(db, scheduled.id, owner, GroupingInput(request_id=uuid4(), seed=0))
    members = [member.user_id for team in proposal.teams for member in team.members]
    assert len(members) == len(set(members)) == 100 and set(members) == set(people)
    assert all(3 <= len(team.members) <= 5 for team in proposal.teams)
    assert proposal.score <= proposal.baseline_score
    assert proposal.score < sum(history.values())
    roster = db.get(Event, result.roster_event_id)
    assert roster is not None and roster.status == "GROUPS_FINALIZED"
    view = teams.roster(db, roster, owner)
    assert Counter(member.status for team in view.teams for member in team.members) == {
        "DECLINED": 1,
        "WITHDRAWN": 1,
        "CONFIRMED": 6,
        "PENDING": 92,
    }
    assert Counter(team.status for team in view.teams) == {
        "NEEDS_ATTENTION": 2,
        "READY": 2,
        "AWAITING_CONFIRMATIONS": 29,
    }
    repaired = teams.repair(
        db,
        roster.id,
        view.teams[0].id,
        owner,
        OwnerAction(version=view.version, request_id=uuid4()),
        "replace",
    )
    replacement = db.scalar(
        select(Assignment).where(
            Assignment.event_id == roster.id,
            Assignment.user_id == identity("integration", "member-101"),
        )
    )
    assert replacement is not None and replacement.status == "PENDING"
    assert sum(team.status == "NEEDS_ATTENTION" for team in repaired.teams) == 1
    member = db.get(User, identity("integration", "member-1"))
    assert member is not None and member.email == member_email("integration", 1)
    assert verify_password(PASSWORD, member.password_hash)


def test_repeat_preserves_changes_and_password(db: Session, owner: User) -> None:
    result = seed(db, owner.email, "repeat", PASSWORD)
    event = db.get(Event, result.scheduled_event_id)
    assert event is not None
    event.title = "Edited in UI"
    user = db.get(User, identity("repeat", "member-1"))
    assert user is not None
    old_hash = user.password_hash
    repeated = seed(db, owner.email, "repeat", "Different-demo-password!")
    assert not repeated.created and repeated.scheduled_event_id == result.scheduled_event_id
    assert event.title == "Edited in UI" and user.password_hash == old_hash
    assert db.scalar(select(func.count()).select_from(Event)) == 5
    assert (
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "demo.seeded")
        )
        == 1
    )
    other = User(
        name="Other", email="other-owner@example.com", password_hash="unused", role="organizer"
    )
    db.add(other)
    db.flush()
    with pytest.raises(ValueError, match="another organizer"):
        seed(db, other.email, "repeat", PASSWORD)


def test_invalid_inputs_and_collisions_preserve_existing_users(db: Session, owner: User) -> None:
    for email, namespace, password, message in [
        ("missing@example.com", "fresh", PASSWORD, "organizer"),
        (owner.email, "../bad", PASSWORD, "Namespace"),
        (owner.email, "fresh", "short", "password"),
    ]:
        with pytest.raises(ValueError, match=message):
            seed(db, email, namespace, password)
    person = User(
        name="Real person",
        email=member_email("collision", 1),
        password_hash="keep-this",
        role="participant",
    )
    db.add(person)
    db.flush()
    with pytest.raises(ValueError, match="identity already exists"):
        seed(db, owner.email, "collision", PASSWORD)
    assert person.password_hash == "keep-this" and person.name == "Real person"
    assert db.scalar(select(func.count()).select_from(Event)) == 0
    with pytest.raises(ValueError, match="organizer"):
        seed(db, person.email, "fresh", PASSWORD)


def test_seed_failure_rolls_back_all_demo_rows(db: Session, owner: User) -> None:
    with pytest.raises(RuntimeError, match="fixture failure"), db.begin_nested():
        with patch(
            "app.services.demo_data.teams.finalize", side_effect=RuntimeError("fixture failure")
        ):
            seed(db, owner.email, "rollback", PASSWORD)
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(Event)) == 0
