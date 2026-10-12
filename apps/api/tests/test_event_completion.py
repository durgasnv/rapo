from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_grouping import create, grouping_event  # noqa: F401 -- injected fixture
from test_registrations import race_setup  # noqa: F401 -- committed concurrency fixture
from test_teams import as_user, finalized  # noqa: F401 -- injected fixture

from app.models import (
    Assignment,
    AuditLog,
    Event,
    FinalTeam,
    GroupingRun,
    LoginSession,
    Registration,
    Team,
    TeamMember,
    User,
)
from app.schemas.events import EventInput
from app.security import COOKIE_NAME, token_hash
from app.services.grouping import inputs

pytestmark = pytest.mark.database
DATES = (
    "start_at",
    "end_at",
    "registration_opens_at",
    "registration_closes_at",
    "grouping_at",
    "confirmation_deadline",
)


def end_event(db, event):
    db.refresh(event)
    for field in DATES:
        setattr(event, field, getattr(event, field) - timedelta(days=30))
    db.commit()


def complete(client, event, version=None):
    return client.post(
        f"/events/{event.id}/complete",
        json={"version": event.version if version is None else version},
    )


def test_completion_preserves_roster_and_counts_history_once(client, db, finalized):  # noqa: F811 -- injected fixture
    event, users, _, _ = finalized
    future = Event(
        **EventInput.model_validate(event).model_dump(),
        organizer_id=event.organizer_id,
        status="PUBLISHED",
    )
    db.add(future)
    db.flush()
    db.add_all(
        [
            Registration(event_id=future.id, user_id=u.id, status="REGISTERED", queue_number=i + 1)
            for i, u in enumerate(users[:6])
        ]
    )
    assignments = list(
        db.scalars(
            select(Assignment)
            .where(Assignment.event_id == event.id)
            .order_by(Assignment.team_id, Assignment.user_id)
        )
    )
    # Retain the actual teams while varying confirmation and dropout outcomes.
    for row, status in zip(
        assignments,
        ["CONFIRMED", "PENDING", "DECLINED", "WITHDRAWN", "CONFIRMED", "CONFIRMED"],
        strict=True,
    ):
        row.status = status
    db.commit()
    end_event(db, event)
    assert inputs(db, future)[1] == {}
    old_preview = create(client, future).json()
    before_version = event.version
    response = complete(client, event)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["version"] == before_version + 1
    # Retry with the original (now stale) version after a lost successful response.
    assert complete(client, event, before_version).json() == response.json()
    db.expire_all()
    history = inputs(db, future)[1]
    included = sorted([a.user_id for a in assignments if a.status in {"PENDING", "CONFIRMED"}])
    team_by_user = {row.user_id: row.team_id for row in assignments}
    assert history == {
        (a, b): 1
        for i, a in enumerate(included)
        for b in included[i + 1 :]
        if team_by_user[a] == team_by_user[b]
    }
    assert len(history) == 2
    audit = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.event_id == event.id, AuditLog.action == "event.completed"
            )
        )
    )
    assert len(audit) == 1
    assert audit[0].before_json == {"status": "GROUPS_FINALIZED", "version": before_version}
    assert audit[0].after_json == {"status": "COMPLETED", "version": before_version + 1}
    assert client.get(f"/events/{event.id}").json()["status"] == "COMPLETED"
    roster = client.get(f"/events/{event.id}/teams").json()
    assert not roster["confirmation_open"] and not roster["withdrawal_open"]
    assert sum(len(t["members"]) for t in roster["teams"]) == 6
    version = client.get(f"/organizer/events/{future.id}").json()["version"]
    stale = client.post(
        f"/events/{future.id}/grouping-runs/{old_preview['id']}/finalize", json={"version": version}
    )
    assert stale.status_code == 409
    new_preview = create(client, future).json()
    assert db.get(GroupingRun, UUID(new_preview["id"])).history_snapshot
    assert (
        client.post(
            f"/events/{event.id}/cancel", json={"version": response.json()["version"]}
        ).status_code
        == 409
    )
    as_user(client, db, db.get(User, included[0]))
    private = client.get(f"/events/{event.id}/teams")
    assert private.status_code == 200 and len(private.json()["teams"]) == 1
    assert {m["user_id"] for m in private.json()["teams"][0]["members"]} == {
        str(person) for person in included if team_by_user[person] == team_by_user[included[0]]
    }
    assert client.post(f"/events/{event.id}/teams/withdraw").status_code == 409


@pytest.mark.parametrize("status", ["DRAFT", "PUBLISHED", "GROUPS_PROPOSED", "CANCELLED"])
def test_completion_rejects_unfinalized_states(client, db, finalized, status):  # noqa: F811 -- injected fixture
    event, *_ = finalized
    end_event(db, event)
    event.status = status
    db.commit()
    assert complete(client, event).status_code == 409
    assert not db.scalar(select(AuditLog.id).where(AuditLog.action == "event.completed"))


def test_completion_checks_end_time_version_and_final_roster(client, db, finalized):  # noqa: F811 -- injected fixture
    event, *_ = finalized
    db.refresh(event)
    assert "must end" in complete(client, event).json()["detail"]
    end_event(db, event)
    assert complete(client, event, event.version + 1).status_code == 409
    # An event status alone is not sufficient evidence of finalized assignments.
    db.execute(delete(Assignment).where(Assignment.event_id == event.id))
    db.execute(delete(FinalTeam).where(FinalTeam.event_id == event.id))
    db.commit()
    assert complete(client, event).status_code == 409


def test_completion_end_boundary_and_in_progress(client, db, finalized):  # noqa: F811 -- injected fixture
    event, *_ = finalized
    db.refresh(event)
    event.status = "IN_PROGRESS"
    db.commit()
    with patch("app.services.event_completion.utcnow", return_value=event.end_at):
        assert complete(client, event).status_code == 200


def test_completion_enforces_roles_ownership_and_csrf(client, db, finalized):  # noqa: F811 -- injected fixture
    event, users, *_ = finalized
    end_event(db, event)
    assert (
        client.post(
            f"/events/{event.id}/complete",
            json={"version": event.version},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )
    as_user(client, db, users[0])
    assert complete(client, event).status_code == 403
    users[0].role = "organizer"
    db.commit()
    assert complete(client, event).status_code == 404
    client.cookies.clear()
    assert complete(client, event).status_code == 401


def test_concurrent_completion_commits_once(race_setup, database_engine):  # noqa: F811
    app, event_id, tokens = race_setup
    with Session(database_engine) as db:
        event = db.get(Event, event_id)
        owner = db.get(User, event.organizer_id)
        owner.role = "organizer"
        event.capacity, event.min_team_size, event.max_team_size = 4, 2, 2
        from app.models import utcnow

        event.registration_opens_at = utcnow() - timedelta(days=2)
        event.registration_closes_at = utcnow() - timedelta(days=1)
        ids = list(
            db.scalars(
                select(LoginSession.user_id).where(
                    LoginSession.token_hash.in_([token_hash(token) for token in tokens])
                )
            )
        )
        db.add_all(
            [
                Registration(
                    event_id=event_id, user_id=person, status="REGISTERED", queue_number=i + 1
                )
                for i, person in enumerate(ids)
            ]
        )
        db.commit()
    try:
        with TestClient(app, base_url="http://127.0.0.1:8000") as client:
            client.cookies.set(COOKIE_NAME, tokens[0])
            client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": "race-csrf"})
            with Session(database_engine) as db:
                event = db.get(Event, event_id)
                preview = create(client, event).json()
                version = client.get(f"/organizer/events/{event_id}").json()["version"]
                finalized_response = client.post(
                    f"/events/{event_id}/grouping-runs/{preview['id']}/finalize",
                    json={"version": version},
                )
                assert finalized_response.status_code == 200
                db.refresh(event)
                end_event(db, event)
                version = event.version
        barrier = Barrier(2)

        def finish():
            with TestClient(app, base_url="http://127.0.0.1:8000") as client:
                client.cookies.set(COOKIE_NAME, tokens[0])
                client.headers.update(
                    {"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": "race-csrf"}
                )
                barrier.wait(timeout=10)
                return client.post(
                    f"/events/{event_id}/complete", json={"version": version}
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: finish(), range(2)))
        assert results == [200, 200]
        with Session(database_engine) as db:
            assert db.get(Event, event_id).version == version + 1
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.event_id == event_id, AuditLog.action == "event.completed")
                )
                == 1
            )
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(Assignment).where(Assignment.event_id == event_id))
            connection.execute(delete(FinalTeam).where(FinalTeam.event_id == event_id))
            runs = select(GroupingRun.id).where(GroupingRun.event_id == event_id)
            connection.execute(delete(TeamMember).where(TeamMember.run_id.in_(runs)))
            connection.execute(delete(Team).where(Team.run_id.in_(runs)))
            connection.execute(delete(GroupingRun).where(GroupingRun.event_id == event_id))


def test_completion_rolls_back_if_audit_write_fails(client, db, finalized):  # noqa: F811
    from sqlalchemy.exc import IntegrityError

    event, *_ = finalized
    end_event(db, event)
    version = event.version

    def invalid_audit(**values):
        return AuditLog(**(values | {"actor_id": uuid4()}))

    with (
        patch("app.services.event_completion.AuditLog", side_effect=invalid_audit),
        pytest.raises(IntegrityError),
    ):
        complete(client, event)
    db.expire_all()
    assert event.status == "GROUPS_FINALIZED" and event.version == version
    assert not db.scalar(select(AuditLog.id).where(AuditLog.action == "event.completed"))
