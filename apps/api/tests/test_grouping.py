from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth import register
from test_events import event_body, make_organizer
from test_registrations import race_setup  # noqa: F401 -- shared concurrency fixture

from app.models import AuditLog, Event, GroupingRun, Registration, Team, TeamMember, User, utcnow
from app.schemas.events import EventInput
from app.security import COOKIE_NAME
from app.services.grouping import inputs
from app.services.registrations import withdraw

pytestmark = pytest.mark.database


@pytest.fixture
def grouping_event(client: TestClient, db: Session) -> tuple[Event, list[User]]:
    make_organizer(client, db)
    owner = db.scalar(select(User).where(User.email == "owner@example.com"))
    assert owner is not None
    event = Event(
        **EventInput.model_validate(
            event_body()
            | {
                "capacity": None,
                "min_team_size": 2,
                "max_team_size": 3,
                "registration_opens_at": utcnow() - timedelta(days=2),
                "registration_closes_at": utcnow() - timedelta(days=1),
            }
        ).model_dump(),
        organizer_id=owner.id,
        status="PUBLISHED",
    )
    db.add(event)
    users = [
        User(name=f"Person {i}", email=f"person-{i}@example.com", password_hash="unused")
        for i in range(8)
    ]
    db.add_all(users)
    db.flush()
    db.add_all(
        [
            Registration(
                event_id=event.id,
                user_id=user.id,
                status="REGISTERED" if i < 6 else "WAITLISTED" if i == 6 else "CANCELLED",
                queue_number=i + 1,
            )
            for i, user in enumerate(users)
        ]
    )
    db.commit()
    return event, users


def history_event(
    db: Session,
    current: Event,
    users: list[User],
    *,
    status: str = "COMPLETED",
    run_status: str = "FINALIZED",
) -> GroupingRun:
    body = EventInput.model_validate(current).model_dump()
    for key in [
        "start_at",
        "end_at",
        "registration_opens_at",
        "registration_closes_at",
        "grouping_at",
        "confirmation_deadline",
    ]:
        body[key] -= timedelta(days=30)
    event = Event(**body, organizer_id=current.organizer_id, status=status)
    db.add(event)
    db.flush()
    run = GroupingRun(
        event_id=event.id,
        request_id=uuid4(),
        created_by=current.organizer_id,
        status=run_status,
        algorithm_version="historical-test",
        seed=0,
        input_hash="0" * 64,
        min_team_size=current.min_team_size,
        max_team_size=current.max_team_size,
        score=0,
        fairness=0,
        baseline_score=0,
        baseline_fairness=0,
        evaluations=0,
        history_snapshot=[],
    )
    db.add(run)
    db.flush()
    team = Team(run_id=run.id, number=1, score=0, explanation="Historical test team")
    db.add(team)
    db.flush()
    db.add_all([TeamMember(team_id=team.id, run_id=run.id, user_id=user.id) for user in users])
    db.commit()
    return run


def create(client: TestClient, event: Event, **overrides):
    return client.post(
        f"/events/{event.id}/grouping-runs",
        json={
            "seed": 42,
            "request_id": str(uuid4()),
            **overrides,
        },
    )


def test_preview_history_eligibility_persistence_and_retry(client, db, grouping_event):
    event, users = grouping_event
    history_event(db, event, users[:6])
    history_event(db, event, users[:6], status="CANCELLED")
    history_event(db, event, users[:6], run_status="PROPOSED")
    ids, history, _ = inputs(db, event)
    assert len(ids) == 6 and len(history) == 15 and set(history.values()) == {1}
    assert client.get(f"/events/{event.id}/grouping-runs/latest").json() is None
    key = str(uuid4())
    response = create(client, event, request_id=key)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["status"] == "PROPOSED" and not result["stale"]
    assert result["score"] == 3 and result["fairness"] == 6
    assert len(result["teams"]) == 3
    assert {m["user_id"] for t in result["teams"] for m in t["members"]} == {
        str(user.id) for user in users[:6]
    }
    assert all(len(t["members"]) == 2 and t["score"] == 1 for t in result["teams"])
    assert "email" not in response.text and "history_snapshot" not in response.text
    assert create(client, event, request_id=key).json() == result
    assert create(client, event, request_id=key, seed=1).status_code == 409
    saved = client.get(f"/events/{event.id}/grouping-runs/{result['id']}")
    assert saved.json() == result
    assert client.get(f"/events/{event.id}/grouping-runs/latest").json() == result
    assert client.get(f"/events/{event.id}").json()["status"] == "GROUPS_PROPOSED"
    assert client.get("/events").json()["items"][0]["id"] == str(event.id)
    assert (
        db.scalar(
            select(func.count()).select_from(GroupingRun).where(GroupingRun.event_id == event.id)
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_id == event.id, AuditLog.action == "grouping.proposed")
        )
        == 1
    )


def test_preview_permission_csrf_and_private_reads(client, db, grouping_event):
    event, _ = grouping_event
    result = create(client, event).json()
    paths = [
        f"/events/{event.id}/grouping-runs/latest",
        f"/events/{event.id}/grouping-runs/{result['id']}",
    ]
    assert create(client, event, seed=-1).status_code == 422
    assert client.post(f"/events/{event.id}/grouping-runs", json={"seed": 0}).status_code == 422
    assert (
        client.post(
            f"/events/{event.id}/grouping-runs",
            json={"seed": 0, "request_id": str(uuid4())},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )
    register(client, "participant@example.com")
    assert create(client, event).status_code == 403
    assert all(client.get(path).status_code == 403 for path in paths)
    make_organizer(client, db, "other-owner@example.com")
    assert create(client, event).status_code == 404
    assert all(client.get(path).status_code == 404 for path in paths)
    assert client.get(f"/events/{uuid4()}/grouping-runs/latest").status_code == 404
    client.cookies.clear()
    for path in paths:
        response = client.get(path)
        assert response.status_code == 401 and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "boundary,allowed",
    [
        ("before_close", False),
        ("at_close", True),
        ("at_start", False),
    ],
)
def test_generation_time_boundaries(client, db, grouping_event, boundary, allowed):
    event, _ = grouping_event
    now = event.registration_closes_at
    if boundary == "before_close":
        now -= timedelta(microseconds=1)
    elif boundary == "at_start":
        now = event.start_at
    with patch("app.services.grouping.utcnow", return_value=now):
        result = create(client, event)
    assert result.status_code == (200 if allowed else 409), result.text


@pytest.mark.parametrize("status", ["DRAFT", "CANCELLED", "COMPLETED"])
def test_inactive_events_cannot_group(client, db, grouping_event, status):
    event, _ = grouping_event
    event.status = status
    db.commit()
    assert create(client, event).status_code == 409


@pytest.mark.parametrize(
    "count,minimum,maximum,code",
    [
        (0, 2, 3, "no_participants"),
        (1, 2, 3, "too_few"),
        (6, 4, 4, "unpartitionable"),
        (101, 2, 3, "participant_limit"),
    ],
)
def test_infeasibility_is_typed_and_does_not_write_proposal(
    client, db, grouping_event, count, minimum, maximum, code
):
    event, users = grouping_event
    db.execute(delete(Registration).where(Registration.event_id == event.id))
    if count > len(users):
        users += [
            User(name=f"Extra {i}", email=f"extra-{i}@example.com", password_hash="unused")
            for i in range(count - len(users))
        ]
        db.add_all(users)
        db.flush()
    db.add_all(
        [
            Registration(
                event_id=event.id, user_id=user.id, status="REGISTERED", queue_number=i + 1
            )
            for i, user in enumerate(users[:count])
        ]
    )
    event.min_team_size, event.max_team_size = minimum, maximum
    db.commit()
    response = create(client, event)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == code
    assert client.get(f"/events/{event.id}/grouping-runs/latest").json() is None
    db.refresh(event)
    assert event.status == "PUBLISHED"


def test_withdrawal_promotion_and_history_changes_mark_preview_stale(client, db, grouping_event):
    event, users = grouping_event
    result = create(client, event).json()
    path = f"/events/{event.id}/grouping-runs/{result['id']}"
    # A valid pre-grouping withdrawal promotes the waiting user and changes the input hash.
    db.refresh(event)
    state = withdraw(db, event.id, users[0].id)
    db.commit()
    assert state.registered_count == 6 and state.waitlisted_count == 0
    stale = client.get(path).json()
    assert stale["stale"] and stale["teams"] == result["teams"]
    new = create(client, event).json()
    assert not new["stale"] and new["id"] != result["id"]
    history_event(db, event, users[1:6])
    assert client.get(f"/events/{event.id}/grouping-runs/{new['id']}").json()["stale"]
    new = create(client, event).json()
    current = client.get(f"/organizer/events/{event.id}").json()
    assert (
        client.post(f"/events/{event.id}/cancel", json={"version": current["version"]}).status_code
        == 200
    )
    assert client.get(f"/events/{event.id}/grouping-runs/{new['id']}").json()["stale"]


def test_failed_generation_rolls_back_all_writes(client, db, grouping_event):
    event, _ = grouping_event
    with patch("app.services.grouping.output", side_effect=RuntimeError("response failure")):
        with pytest.raises(RuntimeError, match="response failure"):
            create(client, event)
    assert client.get(f"/events/{event.id}/grouping-runs/latest").json() is None
    db.refresh(event)
    assert event.status == "PUBLISHED"
    assert db.scalar(select(func.count()).select_from(Team)) == 0


def test_database_prevents_duplicate_members_and_cross_run_membership(client, db, grouping_event):
    event, users = grouping_event
    first = create(client, event).json()
    second = create(client, event).json()
    member = db.scalar(select(TeamMember).where(TeamMember.run_id == UUID(first["id"])))
    other_team = db.scalar(select(Team).where(Team.run_id == UUID(second["id"])))
    assert member is not None and other_team is not None
    for team_id, run_id, user_id, constraint in [
        (member.team_id, member.run_id, member.user_id, "member_run_user"),
        (other_team.id, member.run_id, users[6].id, "team_members_team_id_run_id_fkey"),
    ]:
        with pytest.raises(IntegrityError) as error, db.begin_nested():
            db.add(TeamMember(team_id=team_id, run_id=run_id, user_id=user_id))
            db.flush()
        assert error.value.orig.diag.constraint_name == constraint
    first_run = db.get(GroupingRun, UUID(first["id"]))
    second_run = db.get(GroupingRun, UUID(second["id"]))
    assert first_run is not None and second_run is not None
    assert (first_run.min_team_size, first_run.max_team_size) == (2, 3)
    first_run.status = "FINALIZED"
    db.flush()
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        second_run.status = "FINALIZED"
        db.flush()
    assert error.value.orig.diag.constraint_name == "uq_finalized_grouping_event"


def test_concurrent_grouping_retries_create_one_run(
    race_setup,  # noqa: F811 -- injected shared fixture
    database_engine: Engine,
):
    app, event_id, tokens = race_setup
    with Session(database_engine) as db:
        event = db.get(Event, event_id)
        assert event is not None
        owner = db.get(User, event.organizer_id)
        assert owner is not None
        owner.role = "organizer"
        event.registration_opens_at = utcnow() - timedelta(days=2)
        event.registration_closes_at = utcnow() - timedelta(days=1)
        db.add(
            Registration(event_id=event_id, user_id=owner.id, status="REGISTERED", queue_number=1)
        )
        db.commit()
    barrier, key = Barrier(4), str(uuid4())

    def request():
        with TestClient(app, base_url="http://127.0.0.1:8000") as client:
            client.cookies.set(COOKIE_NAME, tokens[0])
            client.headers["X-CSRF-Token"] = "race-csrf"
            barrier.wait(timeout=10)
            response = client.post(
                f"/events/{event_id}/grouping-runs", json={"request_id": key, "seed": 0}
            )
            assert response.status_code == 200, response.text
            return response.json()["id"]

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(request) for _ in range(4)]
            assert len({f.result(timeout=30) for f in futures}) == 1
        with Session(database_engine) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(GroupingRun)
                    .where(GroupingRun.event_id == event_id)
                )
                == 1
            )
    finally:
        with database_engine.begin() as connection:
            runs = select(GroupingRun.id).where(GroupingRun.event_id == event_id)
            connection.execute(delete(TeamMember).where(TeamMember.run_id.in_(runs)))
            connection.execute(delete(Team).where(Team.run_id.in_(runs)))
            connection.execute(delete(GroupingRun).where(GroupingRun.event_id == event_id))
