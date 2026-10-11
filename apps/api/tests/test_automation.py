from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_grouping import create, grouping_event  # noqa: F401
from test_registrations import race_setup  # noqa: F401
from test_teams import as_user, finalized, get_roster, owner, owner_action  # noqa: F401

from app.jobs.grouping import process_one, run_once
from app.models import (
    AuditLog,
    Event,
    GroupingJob,
    GroupingRun,
    LoginSession,
    Notification,
    Registration,
    Team,
    TeamMember,
    User,
    utcnow,
)
from app.schemas.grouping import GroupingInput
from app.security import COOKIE_NAME, token_hash
from app.services import grouping, notifications

pytestmark = pytest.mark.database


@pytest.fixture
def due_event(race_setup, database_engine):  # noqa: F811
    app, event_id, tokens = race_setup
    with Session(database_engine) as db:
        event = db.get(Event, event_id)
        owner = db.get(User, event.organizer_id)
        owner.role = "organizer"
        now = utcnow()
        event.registration_opens_at = now - timedelta(days=2)
        event.registration_closes_at = now - timedelta(hours=2)
        event.grouping_at = now - timedelta(hours=1)
        event.capacity, event.min_team_size, event.max_team_size = 2, 1, 2
        ids = [db.get(LoginSession, token_hash(t)).user_id for t in tokens]
        db.add_all(
            [
                Registration(
                    event_id=event_id,
                    user_id=p,
                    status="REGISTERED" if i < 2 else "WAITLISTED",
                    queue_number=i + 1,
                )
                for i, p in enumerate(ids[1:])
            ]
        )
        db.commit()
    try:
        yield app, event_id, tokens
    finally:
        with database_engine.begin() as conn:
            conn.execute(delete(GroupingJob).where(GroupingJob.event_id == event_id))
            runs = select(GroupingRun.id).where(GroupingRun.event_id == event_id)
            conn.execute(delete(TeamMember).where(TeamMember.run_id.in_(runs)))
            conn.execute(delete(Team).where(Team.run_id.in_(runs)))
            conn.execute(delete(GroupingRun).where(GroupingRun.event_id == event_id))


def auth_client(app, token):
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    client.cookies.set(COOKIE_NAME, token)
    client.headers.update({"X-CSRF-Token": "race-csrf", "Origin": "http://127.0.0.1:3000"})
    return client


def test_due_worker_persists_one_preview_job_audit_and_private_notice(due_event, database_engine):
    app, eid, tokens = due_event
    assert run_once(database_engine) == {"SUCCEEDED": 1}
    assert run_once(database_engine) == {}
    with Session(database_engine) as db:
        job = db.get(GroupingJob, eid)
        event = db.get(Event, eid)
        assert job.status == "SUCCEEDED" and job.attempts == 1
        assert event.status == "GROUPS_PROPOSED"
        assert db.scalar(select(func.count()).select_from(GroupingRun)) == 1
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "grouping.scheduled")
            )
            == 1
        )
    with auth_client(app, tokens[0]) as client:
        response = client.get(f"/events/{eid}/grouping-job")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["status"] == "SUCCEEDED"
        assert client.get("/me/notifications").json()["items"][0]["kind"] == "GROUPING_READY"
    with auth_client(app, tokens[1]) as client:
        assert client.get(f"/events/{eid}/grouping-job").status_code == 403
        assert client.get("/me/notifications").json()["total"] == 0


@pytest.mark.parametrize(
    "condition",
    ["future", "registration_open", "draft", "cancelled", "finalized", "started", "deadline"],
)
def test_worker_skips_ineligible_events(due_event, database_engine, condition):
    _, eid, _ = due_event
    with Session(database_engine) as db:
        e = db.get(Event, eid)
        now = utcnow()
        if condition == "future":
            e.grouping_at = now + timedelta(hours=1)
        elif condition == "registration_open":
            e.registration_closes_at = now + timedelta(minutes=1)
            e.grouping_at = now + timedelta(hours=1)
        elif condition in {"draft", "cancelled", "finalized"}:
            e.status = {
                "draft": "DRAFT",
                "cancelled": "CANCELLED",
                "finalized": "GROUPS_FINALIZED",
            }[condition]
        elif condition == "started":
            e.start_at = now
            e.confirmation_deadline = now
        else:
            e.confirmation_deadline = now
        db.commit()
    assert process_one(database_engine) is None
    with Session(database_engine) as db:
        assert db.get(GroupingJob, eid) is None


def test_blocked_retry_backoff_dedup_and_recovery(due_event, database_engine):
    _, eid, _ = due_event
    with Session(database_engine) as db:
        db.get(Event, eid).min_team_size = 2
        db.get(Event, eid).max_team_size = 2
        seat = db.scalar(
            select(Registration).where(
                Registration.event_id == eid, Registration.status == "REGISTERED"
            )
        )
        seat.status = "CANCELLED"
        db.commit()
    assert run_once(database_engine) == {"BLOCKED": 1}
    assert run_once(database_engine) == {}
    with Session(database_engine) as db:
        job = db.get(GroupingJob, eid)
        assert job.code == "too_few" and job.run_id is None
        job.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert process_one(database_engine) == "BLOCKED"
    with Session(database_engine) as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
        db.get(GroupingJob, eid).next_attempt_at = utcnow() - timedelta(seconds=1)
        db.scalar(
            select(Registration).where(
                Registration.event_id == eid, Registration.status == "CANCELLED"
            )
        ).status = "REGISTERED"
        db.commit()
    assert process_one(database_engine) == "SUCCEEDED"
    with Session(database_engine) as db:
        assert db.get(GroupingJob, eid).attempts == 3
        assert db.scalar(select(func.count()).select_from(GroupingRun)) == 1
        assert db.scalar(select(func.count()).select_from(Notification)) == 2


@pytest.mark.parametrize("failure", ["response", "notification", "crash"])
def test_worker_failure_rolls_back_and_recovers(due_event, database_engine, failure):
    _, eid, _ = due_event
    target = (
        "app.services.grouping.output"
        if failure in {"response", "crash"}
        else "app.jobs.grouping.notifications.send"
    )
    error = (
        KeyboardInterrupt("synthetic crash")
        if failure == "crash"
        else RuntimeError("private error detail")
    )
    with patch(target, side_effect=error):
        if failure == "crash":
            with pytest.raises(KeyboardInterrupt):
                process_one(database_engine)
        else:
            assert process_one(database_engine) == "FAILED"
    with Session(database_engine) as db:
        assert db.scalar(select(func.count()).select_from(GroupingRun)) == 0
        assert db.scalar(select(func.count()).select_from(Team)) == 0
        assert db.scalar(select(func.count()).select_from(Notification)) == 0
        assert db.get(Event, eid).status == "PUBLISHED"
        job = db.get(GroupingJob, eid)
        if failure == "crash":
            assert job is None
        else:
            assert "private" not in job.message
            job.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert process_one(database_engine) == "SUCCEEDED"


@pytest.mark.parametrize("manual", [False, True])
def test_concurrent_workers_and_manual_preview_preserve_intent(due_event, database_engine, manual):
    _, eid, _ = due_event
    barrier = Barrier(4)

    def run(i):
        barrier.wait(timeout=10)
        if manual and i == 0:
            with Session(database_engine) as db, db.begin():
                event = db.get(Event, eid)
                actor = db.get(User, event.organizer_id)
                grouping.create(db, eid, actor, GroupingInput(request_id=uuid4(), seed=1))
            return
        process_one(database_engine)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(run, range(4)))
    with Session(database_engine) as db:
        runs = list(db.scalars(select(GroupingRun)))
        # A deliberate manual generation may follow the scheduled preview; retries
        # of the worker must never add another scheduled run.
        assert len(runs) in ({1, 2} if manual else {1})
        assert sum(run.seed != 1 for run in runs) <= 1
        job = db.get(GroupingJob, eid)
        if job:
            assert job.status == "SUCCEEDED" and job.attempts == 1
            assert any(run.id == job.run_id for run in runs)
        assert db.get(Event, eid).status == "GROUPS_PROPOSED"


def test_existing_manual_preview_is_preserved(due_event, database_engine):
    _, eid, _ = due_event
    with Session(database_engine) as db, db.begin():
        event = db.get(Event, eid)
        result = grouping.create(
            db, eid, db.get(User, event.organizer_id), GroupingInput(request_id=uuid4(), seed=9)
        )
        run_id = result.id
    assert process_one(database_engine) is None
    with Session(database_engine) as db:
        assert db.get(GroupingJob, eid) is None
        assert db.get(GroupingRun, run_id).seed == 9


def test_notifications_ownership_csrf_read_retry_and_pagination(client, db, grouping_event):  # noqa: F811
    event, users = grouping_event
    for i in range(23):
        notifications.send(db, event, event.organizer_id, "TEST", "A private update.", f"test:{i}")
    notifications.send(db, event, event.organizer_id, "TEST", "A private update.", "test:0")
    db.commit()
    response = client.get("/me/notifications?limit=20")
    assert response.headers["cache-control"] == "no-store"
    page = response.json()
    assert len(page["items"]) == 20 and page["total"] == 23 and page["unread_count"] == 23
    assert len(client.get("/me/notifications?offset=20").json()["items"]) == 3
    nid = page["items"][0]["id"]
    assert (
        client.post(f"/me/notifications/{nid}/read", headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    first = client.post(f"/me/notifications/{nid}/read").json()
    assert first["read_at"] and client.post(f"/me/notifications/{nid}/read").json() == first
    assert client.get("/me/notifications?unread_only=true").json()["total"] == 22
    for suffix in ["?offset=-1", "?limit=101"]:
        assert client.get("/me/notifications" + suffix).status_code == 422
    as_user(client, db, users[0])
    assert client.get("/me/notifications").json()["items"] == []
    assert client.post(f"/me/notifications/{nid}/read").status_code == 404
    client.cookies.clear()
    assert client.get("/me/notifications").status_code == 401


def test_assignment_changes_notify_only_affected_members_and_retry_once(client, db, finalized):  # noqa: F811
    event, users, run, roster = finalized
    assert db.scalar(select(func.count()).select_from(Notification)) == 7
    current = client.get("/organizer/events/" + str(event.id)).json()
    assert (
        client.post(
            f"/events/{event.id}/grouping-runs/{run['id']}/finalize",
            json={"version": current["version"]},
        ).status_code
        == 200
    )
    assert db.scalar(select(func.count()).select_from(Notification)) == 7
    as_user(client, db, users[0])
    own_team = get_roster(client, event)["teams"][0]
    assert client.post(f"/events/{event.id}/teams/withdraw").status_code == 200
    assert client.post(f"/events/{event.id}/teams/withdraw").status_code == 200
    peer = next(UUID(m["user_id"]) for m in own_team["members"] if m["user_id"] != str(users[0].id))
    rows = list(db.scalars(select(Notification).where(Notification.kind == "TEAM_CHANGED")))
    assert [n.user_id for n in rows] == [peer]
    owner(client, db, event)
    assert owner_action(client, event, f"{own_team['id']}/replace").status_code == 200
    assigned = db.scalars(select(Notification).where(Notification.kind == "TEAM_ASSIGNED")).all()
    assert len(assigned) == 7 and any(n.user_id == users[6].id for n in assigned)
    assert all("email" not in n.message for n in assigned)


def test_notification_failure_rolls_back_roster_finalization(client, db, grouping_event):  # noqa: F811
    event, _ = grouping_event
    run = create(client, event).json()
    version = client.get(f"/organizer/events/{event.id}").json()["version"]
    with patch("app.services.notifications.send", side_effect=RuntimeError("store unavailable")):
        with pytest.raises(RuntimeError):
            client.post(
                f"/events/{event.id}/grouping-runs/{run['id']}/finalize", json={"version": version}
            )
    assert db.scalar(select(func.count()).select_from(Notification)) == 0
    assert db.get(GroupingRun, UUID(run["id"])).status == "PROPOSED"
    assert (
        client.post(
            f"/events/{event.id}/grouping-runs/{run['id']}/finalize", json={"version": version}
        ).status_code
        == 200
    )


def test_promotion_and_cancellation_notifications(client, db, grouping_event):  # noqa: F811
    event, users = grouping_event
    as_user(client, db, users[0])
    assert client.delete(f"/events/{event.id}/registration").status_code == 200
    assert (
        db.scalar(select(Notification).where(Notification.kind == "WAITLIST_PROMOTED")).user_id
        == users[6].id
    )
    owner(client, db, event)
    version = client.get(f"/organizer/events/{event.id}").json()["version"]
    assert client.post(f"/events/{event.id}/cancel", json={"version": version}).status_code == 200
    rows = db.scalars(select(Notification).where(Notification.kind == "EVENT_CANCELLED")).all()
    assert len(rows) == 6 and all(n.destination == "ACCOUNT" for n in rows)
    assert users[0].id not in {n.user_id for n in rows}


def test_cutoff_during_generation_rolls_back_preview(due_event, database_engine):
    app, eid, tokens = due_event
    with Session(database_engine) as db:
        cutoff = db.get(Event, eid).confirmation_deadline
    with patch("app.jobs.grouping.utcnow", side_effect=[utcnow(), cutoff, cutoff]):
        assert process_one(database_engine) == "BLOCKED"
    with Session(database_engine) as db:
        assert db.get(GroupingJob, eid).code == "cutoff_passed"
        assert db.scalar(select(func.count()).select_from(GroupingRun)) == 0
        assert db.get(Event, eid).status == "PUBLISHED"
    with (
        auth_client(app, tokens[0]) as client,
        patch("app.services.scheduling.utcnow", return_value=cutoff),
    ):
        assert client.get(f"/events/{eid}/grouping-job").json()["status"] == "EXPIRED"
    with Session(database_engine) as db:
        other = db.get(User, db.get(LoginSession, token_hash(tokens[1])).user_id)
        other.role = "organizer"
        db.commit()
    with auth_client(app, tokens[1]) as client:
        assert client.get(f"/events/{eid}/grouping-job").status_code == 404


def test_worker_requires_owner_organizer_access(due_event, database_engine):
    _, eid, _ = due_event
    with Session(database_engine) as db:
        event = db.get(Event, eid)
        db.get(User, event.organizer_id).role = "participant"
        db.commit()
    assert process_one(database_engine) == "BLOCKED"
    with Session(database_engine) as db:
        assert db.get(GroupingJob, eid).code == "organizer_unavailable"
        assert db.scalar(select(func.count()).select_from(GroupingRun)) == 0
