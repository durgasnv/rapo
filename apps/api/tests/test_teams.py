import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth import register
from test_events import make_organizer
from test_grouping import create, grouping_event  # noqa: F401 -- shared fixture
from test_registrations import race_setup  # noqa: F401 -- shared committed fixture

from app.models import (
    Assignment,
    AuditLog,
    Event,
    FinalTeam,
    GroupingRun,
    LoginSession,
    Registration,
    RosterAction,
    Team,
    TeamMember,
    User,
    utcnow,
)
from app.security import COOKIE_NAME, token_hash
from app.services.grouping import inputs

pytestmark = pytest.mark.database


@pytest.fixture
def finalized(client, db, grouping_event):  # noqa: F811 -- injected fixture
    event, users = grouping_event
    run = create(client, event).json()
    version = client.get(f"/organizer/events/{event.id}").json()["version"]
    response = client.post(
        f"/events/{event.id}/grouping-runs/{run['id']}/finalize", json={"version": version}
    )
    assert response.status_code == 200, response.text
    return event, users, run, response.json()


def as_user(client, db, user):
    raw = str(uuid4())
    db.add(
        LoginSession(
            token_hash=token_hash(raw),
            user_id=user.id,
            csrf_token="team-csrf",
            expires_at=utcnow() + timedelta(days=1),
        )
    )
    db.commit()
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, raw, domain="127.0.0.1", path="/")
    client.headers["X-CSRF-Token"] = "team-csrf"


def get_roster(client, event):
    response = client.get(f"/events/{event.id}/teams")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def owner(client, db, event):
    as_user(client, db, db.get(User, event.organizer_id))


def owner_action(client, event, suffix, **values):
    current = get_roster(client, event)
    return client.post(
        f"/events/{event.id}/teams/{suffix}",
        json={
            "version": current["version"],
            "request_id": str(uuid4()),
            **values,
        },
    )


def test_finalization_preserves_preview_and_is_idempotent(client, db, finalized):
    event, users, run, roster = finalized
    assert len(roster["teams"]) == 3 and all(
        t["status"] == "AWAITING_CONFIRMATIONS" for t in roster["teams"]
    )
    assert sum(len(t["members"]) for t in roster["teams"]) == 6
    assert (
        client.post(
            f"/events/{event.id}/grouping-runs/{run['id']}/finalize", json={"version": 1}
        ).json()
        == roster
    )
    original = client.get(f"/events/{event.id}/grouping-runs/{run['id']}").json()
    assert original["status"] == "FINALIZED" and original["teams"] == run["teams"]
    assert db.scalar(select(func.count()).select_from(Assignment)) == 6
    assert client.get(f"/events/{event.id}").json()["status"] == "GROUPS_FINALIZED"


def test_stale_corrupt_expired_and_other_proposals_are_rejected(client, db, grouping_event):  # noqa: F811
    event, users = grouping_event
    run = create(client, event).json()
    path = f"/events/{event.id}/grouping-runs/{run['id']}/finalize"
    assert client.post(path, json={"version": 1}).status_code == 409
    version = client.get(f"/organizer/events/{event.id}").json()["version"]
    with patch("app.services.teams.utcnow", return_value=event.confirmation_deadline):
        assert client.post(path, json={"version": version}).status_code == 409
    member = db.scalar(select(TeamMember).where(TeamMember.run_id == UUID(run["id"])))
    db.delete(member)
    db.commit()
    assert client.post(path, json={"version": version}).status_code == 409
    run = create(client, event).json()
    db.refresh(event)
    registration = db.scalar(select(Registration).where(Registration.user_id == users[0].id))
    registration.status = "CANCELLED"
    db.commit()
    response = client.post(
        f"/events/{event.id}/grouping-runs/{run['id']}/finalize", json={"version": event.version}
    )
    assert response.status_code == 409 and "stale" in response.text
    assert db.scalar(select(func.count()).select_from(FinalTeam)) == 0


def test_participants_only_see_their_team_confirm_and_decline(client, db, finalized):
    event, users, _, roster = finalized
    as_user(client, db, users[0])
    own = get_roster(client, event)
    assert len(own["teams"]) == 1
    team = own["teams"][0]
    body = {"decision": "confirm", "team_version": team["version"]}
    path = f"/events/{event.id}/teams/{team['id']}/confirm"
    response = client.post(path, json=body)
    assert response.status_code == 200 and response.json()["own_status"] == "CONFIRMED"
    assert client.post(path, json=body).json() == response.json()
    other_team = next(t for t in roster["teams"] if t["id"] != team["id"])
    assert (
        client.post(f"/events/{event.id}/teams/{other_team['id']}/confirm", json=body).status_code
        == 404
    )
    declined = client.post(path, json={"decision": "decline", "team_version": team["version"]})
    assert declined.status_code == 200 and declined.json()["own_status"] == "DECLINED"
    assert declined.json()["teams"] == []
    owner(client, db, event)
    changed = get_roster(client, event)
    affected = next(t for t in changed["teams"] if t["id"] == team["id"])
    assert affected["status"] == "NEEDS_ATTENTION"
    assert all(m["status"] != "CONFIRMED" for m in affected["members"])


def test_fifo_replacement_retries_and_immutable_proposal(client, db, finalized):
    event, users, run, initial = finalized
    as_user(client, db, users[0])
    own_team = get_roster(client, event)["teams"][0]
    response = client.delete(f"/events/{event.id}/registration")
    assert response.status_code == 200 and response.json()["registration"]["status"] == "CANCELLED"
    assert client.post(f"/events/{event.id}/teams/withdraw").status_code == 200
    owner(client, db, event)
    current = get_roster(client, event)
    body = {"version": current["version"], "request_id": str(uuid4())}
    path = f"/events/{event.id}/teams/{own_team['id']}/replace"
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    changed = response.json()
    active = [
        m for t in changed["teams"] for m in t["members"] if m["status"] in {"PENDING", "CONFIRMED"}
    ]
    assert str(users[6].id) in [m["user_id"] for m in active]
    assert client.post(path, json=body).json() == changed
    assert client.post(path, json=body | {"version": 999}).status_code == 409
    assert owner_action(client, event, f"{own_team['id']}/replace").status_code == 409
    assert (
        client.get(f"/events/{event.id}/grouping-runs/{run['id']}").json()["teams"] == run["teams"]
    )
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "team.replace"))
    assert audit.before_json and audit.after_json and audit.before_json != audit.after_json
    teammate_id = next(
        m["user_id"] for m in own_team["members"] if m["user_id"] != str(users[0].id)
    )
    as_user(client, db, next(u for u in users if str(u.id) == teammate_id))
    assert (
        client.post(
            f"/events/{event.id}/teams/{own_team['id']}/confirm",
            json={
                "decision": "confirm",
                "team_version": own_team["version"],
            },
        ).status_code
        == 409
    )


def test_deadline_missed_members_remain_pending_extension_and_reconfirmation(client, db, finalized):
    event, users, _, _ = finalized
    as_user(client, db, users[0])
    team = get_roster(client, event)["teams"][0]
    with patch("app.services.teams.utcnow", return_value=event.confirmation_deadline):
        current = get_roster(client, event)
        assert current["teams"][0]["status"] == "NEEDS_ATTENTION"
        assert current["own_status"] == "PENDING"
        assert (
            client.post(
                f"/events/{event.id}/teams/{team['id']}/confirm",
                json={"decision": "confirm", "team_version": team["version"]},
            ).status_code
            == 409
        )
        owner(client, db, event)
        assert (
            owner_action(
                client,
                event,
                "deadline",
                confirmation_deadline=(event.start_at + timedelta(seconds=1)).isoformat(),
            ).status_code
            == 422
        )
        extended = owner_action(
            client, event, "deadline", confirmation_deadline=event.start_at.isoformat()
        )
        assert extended.status_code == 200 and extended.json()["confirmation_open"]
    as_user(client, db, users[0])
    assert (
        client.post(
            f"/events/{event.id}/teams/{team['id']}/confirm",
            json={"decision": "confirm", "team_version": team["version"]},
        ).status_code
        == 200
    )


def test_reassignment_validates_both_teams_and_resets_confirmations(client, db, finalized):
    event, users, _, initial = finalized
    as_user(client, db, users[0])
    team = get_roster(client, event)["teams"][0]
    assert (
        client.post(
            f"/events/{event.id}/teams/{team['id']}/confirm",
            json={"decision": "confirm", "team_version": team["version"]},
        ).status_code
        == 200
    )
    owner(client, db, event)
    other = next(t for t in initial["teams"] if t["id"] != team["id"])
    assert (
        owner_action(
            client, event, "reassign", user_id=str(users[0].id), target_team_id=other["id"]
        ).status_code
        == 409
    )
    changed = owner_action(
        client,
        event,
        "reassign",
        user_id=str(users[0].id),
        target_team_id=other["id"],
        swap_user_id=other["members"][0]["user_id"],
    )
    assert changed.status_code == 200, changed.text
    assert all(m["status"] == "PENDING" for t in changed.json()["teams"] for m in t["members"])
    as_user(client, db, users[0])
    assert (
        client.post(
            f"/events/{event.id}/teams/{team['id']}/confirm",
            json={"decision": "confirm", "team_version": team["version"]},
        ).status_code
        == 404
    )


def test_continuation_requires_valid_size_and_no_waitlist_is_clear(client, db, finalized):
    event, users, _, _ = finalized
    as_user(client, db, users[0])
    team = get_roster(client, event)["teams"][0]
    assert client.post(f"/events/{event.id}/teams/withdraw").status_code == 200
    owner(client, db, event)
    assert owner_action(client, event, f"{team['id']}/continue").status_code == 409
    waiting = db.scalar(select(Registration).where(Registration.user_id == users[6].id))
    waiting.status = "CANCELLED"
    db.commit()
    assert "No eligible waitlisted" in owner_action(client, event, f"{team['id']}/replace").text
    # A trusted event configuration fixture permits the one remaining member.
    db.refresh(event)
    event.min_team_size = 1
    db.commit()
    approved = owner_action(client, event, f"{team['id']}/continue")
    assert approved.status_code == 200
    assert next(t for t in approved.json()["teams"] if t["id"] == team["id"])["target_size"] == 1


def test_export_privacy_authorization_csrf_and_formula_escaping(client, db, finalized):
    event, users, _, roster = finalized
    users[0].name = ' =HYPERLINK("evil")'
    db.commit()
    response = client.get(f"/events/{event.id}/teams/export")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    rows = list(csv.reader(io.StringIO(response.text)))
    assert len(rows) == 7 and any(row[3].startswith("' =") for row in rows[1:])
    assert "email" not in response.text
    as_user(client, db, users[0])
    assert client.get(f"/events/{event.id}/teams/export").status_code == 403
    assert owner_action(client, event, f"{roster['teams'][0]['id']}/continue").status_code == 403
    assert (
        client.post(
            f"/events/{event.id}/teams/withdraw", headers={"X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    register(client, "outsider@example.com")
    assert client.get(f"/events/{event.id}/teams").status_code == 404
    make_organizer(client, db, "other-organizer@example.com")
    assert client.get(f"/events/{event.id}/teams/export").status_code == 404
    client.cookies.clear()
    assert client.get(f"/events/{event.id}/teams").status_code == 401


def test_after_start_and_cancellation_stop_mutations(client, db, finalized):
    event, users, _, roster = finalized
    as_user(client, db, users[0])
    with patch("app.services.teams.utcnow", return_value=event.start_at):
        assert client.post(f"/events/{event.id}/teams/withdraw").status_code == 409
    owner(client, db, event)
    current = client.get(f"/organizer/events/{event.id}").json()
    assert (
        client.post(f"/events/{event.id}/cancel", json={"version": current["version"]}).status_code
        == 200
    )
    as_user(client, db, users[0])
    assert not get_roster(client, event)["confirmation_open"]
    assert client.post(f"/events/{event.id}/teams/withdraw").status_code == 409


def test_failed_finalization_rolls_back_assignments(client, db, grouping_event):  # noqa: F811
    event, _ = grouping_event
    run = create(client, event).json()
    current = client.get(f"/organizer/events/{event.id}").json()
    with patch("app.services.teams.roster", side_effect=RuntimeError("response failure")):
        with pytest.raises(RuntimeError, match="response failure"):
            client.post(
                f"/events/{event.id}/grouping-runs/{run['id']}/finalize",
                json={"version": current["version"]},
            )
    assert db.scalar(select(func.count()).select_from(Assignment)) == 0
    assert db.get(GroupingRun, UUID(run["id"])).status == "PROPOSED"


def test_database_prevents_duplicate_assignments(client, db, finalized):
    event, users, _, roster = finalized
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        db.add(
            Assignment(
                event_id=event.id, team_id=UUID(roster["teams"][0]["id"]), user_id=users[0].id
            )
        )
        db.flush()
    assert error.value.orig.diag.constraint_name == "assignment_event_user"


def test_completed_history_uses_actual_roster_and_excludes_withdrawn(client, db, finalized):
    event, users, run, roster = finalized
    as_user(client, db, users[0])
    client.post(f"/events/{event.id}/teams/withdraw")
    db.refresh(event)
    for key in [
        "start_at",
        "end_at",
        "registration_opens_at",
        "registration_closes_at",
        "grouping_at",
        "confirmation_deadline",
    ]:
        setattr(event, key, getattr(event, key) - timedelta(days=30))
    event.status = "COMPLETED"
    db.commit()
    # Query as another future event with the same eligible population.
    from app.schemas.events import EventInput

    body = EventInput.model_validate(event).model_dump()
    for key in [
        "start_at",
        "end_at",
        "registration_opens_at",
        "registration_closes_at",
        "grouping_at",
        "confirmation_deadline",
    ]:
        body[key] += timedelta(days=40)
    future = Event(**body, organizer_id=event.organizer_id, status="PUBLISHED")
    db.add(future)
    db.flush()
    db.add_all(
        [
            Registration(event_id=future.id, user_id=u.id, status="REGISTERED", queue_number=i + 1)
            for i, u in enumerate(users[:6])
        ]
    )
    db.commit()
    _, history, _ = inputs(db, future)
    assert len(history) == 2 and sum(history.values()) == 2
    assert all(users[0].id not in pair for pair in history)


@pytest.mark.parametrize("same_run", [True, False])
def test_competing_finalizations(race_setup, database_engine, same_run):  # noqa: F811
    app, event_id, tokens = race_setup
    with Session(database_engine) as db:
        event = db.get(Event, event_id)
        owner = db.get(User, event.organizer_id)
        owner.role = "organizer"
        event.capacity, event.min_team_size, event.max_team_size = 4, 2, 2
        event.registration_opens_at = utcnow() - timedelta(days=2)
        event.registration_closes_at = utcnow() - timedelta(days=1)
        ids = list(
            db.scalars(
                select(LoginSession.user_id).where(
                    LoginSession.token_hash.in_([token_hash(t) for t in tokens])
                )
            )
        )
        db.add_all(
            [
                Registration(event_id=event_id, user_id=p, status="REGISTERED", queue_number=i + 1)
                for i, p in enumerate(ids)
            ]
        )
        db.commit()

    def request(path, body):
        with TestClient(app, base_url="http://127.0.0.1:8000") as client:
            client.cookies.set(COOKIE_NAME, tokens[0])
            client.headers["X-CSRF-Token"] = "race-csrf"
            return client.post(path, json=body)

    try:
        runs = [
            request(
                f"/events/{event_id}/grouping-runs", {"seed": i, "request_id": str(uuid4())}
            ).json()
            for i in range(2)
        ]
        with Session(database_engine) as db:
            version = db.get(Event, event_id).version
        barrier = Barrier(2)

        def finalize(index):
            barrier.wait(timeout=10)
            return request(
                f"/events/{event_id}/grouping-runs/{runs[0 if same_run else index]['id']}/finalize",
                {"version": version},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(finalize, range(2)))
        assert sorted(results) == ([200, 200] if same_run else [200, 409])
        with Session(database_engine) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Assignment)
                    .where(Assignment.event_id == event_id)
                )
                == 4
            )
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(RosterAction).where(RosterAction.event_id == event_id))
            connection.execute(delete(Assignment).where(Assignment.event_id == event_id))
            connection.execute(delete(FinalTeam).where(FinalTeam.event_id == event_id))
            runs = select(GroupingRun.id).where(GroupingRun.event_id == event_id)
            connection.execute(delete(TeamMember).where(TeamMember.run_id.in_(runs)))
            connection.execute(delete(Team).where(Team.run_id.in_(runs)))
            connection.execute(delete(GroupingRun).where(GroupingRun.event_id == event_id))


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_replacement_claims_waitlisted_user_once(
    race_setup,  # noqa: F811 -- shared fixture
    database_engine,
    same_request,
):
    app, event_id, tokens = race_setup
    with Session(database_engine) as db:
        event = db.get(Event, event_id)
        user = db.get(User, event.organizer_id)
        user.role = "organizer"
        event.capacity, event.min_team_size, event.max_team_size = 2, 2, 3
        event.registration_opens_at = utcnow() - timedelta(days=2)
        event.registration_closes_at = utcnow() - timedelta(days=1)
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

    def request(path, body, token=tokens[0]):
        with TestClient(app, base_url="http://127.0.0.1:8000") as client:
            client.cookies.set(COOKIE_NAME, token)
            client.headers["X-CSRF-Token"] = "race-csrf"
            return client.post(path, json=body)

    try:
        run = request(
            f"/events/{event_id}/grouping-runs", {"request_id": str(uuid4()), "seed": 0}
        ).json()
        with Session(database_engine) as db:
            version = db.get(Event, event_id).version
        finalized = request(
            f"/events/{event_id}/grouping-runs/{run['id']}/finalize", {"version": version}
        ).json()
        team_id = finalized["teams"][0]["id"]
        assert request(f"/events/{event_id}/teams/withdraw", {}, tokens[1]).status_code == 200
        with Session(database_engine) as db:
            version = db.get(Event, event_id).version
        barrier, key = Barrier(2), str(uuid4())

        def replace(index):
            barrier.wait(timeout=10)
            return request(
                f"/events/{event_id}/teams/{team_id}/replace",
                {
                    "version": version,
                    "request_id": key if same_request else str(uuid4()),
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(replace, range(2)))
        assert sorted(results) == ([200, 200] if same_request else [200, 409])
        with Session(database_engine) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Assignment)
                    .where(Assignment.event_id == event_id, Assignment.status == "PENDING")
                )
                == 2
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(RosterAction)
                    .where(RosterAction.event_id == event_id)
                )
                == 1
            )
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(RosterAction).where(RosterAction.event_id == event_id))
            connection.execute(delete(Assignment).where(Assignment.event_id == event_id))
            connection.execute(delete(FinalTeam).where(FinalTeam.event_id == event_id))
            runs = select(GroupingRun.id).where(GroupingRun.event_id == event_id)
            connection.execute(delete(TeamMember).where(TeamMember.run_id.in_(runs)))
            connection.execute(delete(Team).where(Team.run_id.in_(runs)))
            connection.execute(delete(GroupingRun).where(GroupingRun.event_id == event_id))
