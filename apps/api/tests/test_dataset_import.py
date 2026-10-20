import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import combinations
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from pydantic import ValidationError
from sqlalchemy import func, select
from test_teams import as_user

from app.models import Assignment, AuditLog, Event, GroupingRun, Registration, User
from app.schemas.dataset import Dataset
from app.schemas.grouping import GroupingInput
from app.security import verify_password
from app.services import grouping
from app.services.dataset_import import identity, import_dataset, member_email

SOURCE = Path(__file__).resolve().parents[3] / "demo/dataset_college.json"
PASSWORD = "College-test-password!"
NOW = datetime(2026, 10, 20, tzinfo=UTC)
database = pytest.mark.database


@pytest.fixture
def dataset():
    return Dataset.model_validate_json(SOURCE.read_text())


@pytest.fixture
def owner(db):
    user = User(name="Owner", email="owner@example.com", password_hash="keep", role="organizer")
    db.add(user)
    db.flush()
    return user


@pytest.fixture(autouse=True)
def fast_hashes():
    with patch("app.services.dataset_import.hasher", PasswordHasher(time_cost=1, memory_cost=1024)):
        yield


@pytest.mark.parametrize(
    "case",
    ["unknown_member", "duplicate_queue", "missing_assignment", "wrong_team", "count", "size"],
)
def test_reject_invalid_relationships(case):
    body = json.loads(SOURCE.read_text())
    if case == "unknown_member":
        body["registrations"][0]["member_id"] = 9999
    elif case == "duplicate_queue":
        body["registrations"][1]["queue_number"] = body["registrations"][0]["queue_number"]
    elif case == "missing_assignment":
        body["assignments"].pop()
    elif case == "wrong_team":
        body["assignments"][0]["team_number"] = 999
    elif case == "count":
        body["events"][0]["registered_count"] += 1
    else:
        body["completed_event_history"][0]["teams"][0]["members"].pop()
    with pytest.raises(ValidationError):
        Dataset.model_validate(body)


@database
def test_import_rows_and_exact_completed_collaboration_history(db, owner, dataset):
    with patch("app.services.dataset_import.utcnow", return_value=NOW):
        result = import_dataset(db, dataset, owner.email, "college", PASSWORD)
    assert result.created and result.participants == 77 and result.cancelled_registrations == 2
    assert db.scalar(select(func.count()).select_from(User)) == 78
    assert db.scalar(select(func.count()).select_from(User).where(User.role == "organizer")) == 1
    assert db.scalar(select(func.count()).select_from(Event)) == 7
    assert db.scalar(select(func.count()).select_from(Registration)) == 185
    assert db.scalar(select(func.count()).select_from(Assignment)) == 108
    assert db.scalar(select(func.count()).select_from(GroupingRun)) == 3
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 7
    for source_id in (20, 40):
        row = db.scalar(
            select(Registration).where(
                Registration.event_id == result.event_ids["gfu-003"],
                Registration.user_id == identity("college", f"member:{source_id}"),
            )
        )
        assert row.status == "CANCELLED"
    target = db.get(Event, result.event_ids["gfu-004"])
    with patch("app.services.grouping.utcnow", return_value=NOW):
        people, history, _ = grouping.inputs(db, target)
    expected = Counter()
    for completed in dataset.completed_event_history:
        for team in completed.teams:
            ids = sorted(identity("college", f"member:{person}") for person in team.members)
            expected.update((a, b) for a, b in combinations(ids, 2) if a in people and b in people)
    assert history == dict(expected) and history
    user = db.get(User, identity("college", "member:4"))
    assert user.email == member_email("college", 4) and verify_password(
        PASSWORD, user.password_hash
    )
    with patch("app.services.grouping.utcnow", return_value=target.grouping_at):
        proposal = grouping.create(db, target.id, owner, GroupingInput(request_id=uuid4(), seed=4))
    members = [m.user_id for team in proposal.teams for m in team.members]
    assert len(members) == len(set(members)) == 24 and set(members) == set(people)
    assert proposal.score <= proposal.baseline_score
    assert all(3 <= len(team.members) <= 4 for team in proposal.teams)


@database
def test_api_catalog_owner_and_participant_privacy(client, db, owner, dataset):
    result = import_dataset(db, dataset, owner.email, "api", PASSWORD)
    as_user(client, db, owner)
    assert len(client.get("/organizer/events").json()) == 7
    assert client.get("/events").json()["total"] == 3
    finalized = result.event_ids["gfu-003"]
    full = client.get(f"/events/{finalized}/teams")
    assert full.status_code == 200, full.text
    assert len(full.json()["teams"]) == 7
    person = dataset.grouping_runs[0].teams[0].members[0]
    client.cookies.clear()
    response = client.post(
        "/auth/login",
        json={
            "email": member_email("api", person),
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "participant"
    own = client.get(f"/events/{finalized}/teams")
    assert own.status_code == 200, own.text
    assert len(own.json()["teams"]) == 1
    assert client.get("/organizer/events").status_code == 403
    assert client.get(f"/events/{result.event_ids['gfu-006']}").status_code == 404
    assert client.get("/me/registrations").status_code == 200


@database
def test_repeat_and_collision_never_overwrite_existing_data(db, owner, dataset):
    result = import_dataset(db, dataset, owner.email, "repeat", PASSWORD)
    event = db.get(Event, result.event_ids["gfu-004"])
    event.title = "Edited in UI"
    user = db.get(User, identity("repeat", "member:4"))
    previous = user.password_hash
    assert not import_dataset(db, dataset, owner.email, "repeat", "another-password").created
    assert event.title == "Edited in UI" and user.password_hash == previous
    assert owner.password_hash == "keep"
    with pytest.raises(ValueError, match="different source"):
        import_dataset(db, dataset, owner.email, "repeat", PASSWORD, shift_days=1)
    other = User(name="Other", email="other@example.com", password_hash="keep", role="organizer")
    db.add(other)
    db.flush()
    with pytest.raises(ValueError, match="another organizer"):
        import_dataset(db, dataset, other.email, "repeat", PASSWORD)
    with pytest.raises(ValueError, match="organizer"):
        import_dataset(db, dataset, user.email, "new", PASSWORD)
    existing = User(name="Real", email=member_email("collision", 4), password_hash="keep")
    db.add(existing)
    db.flush()
    with pytest.raises(ValueError, match="identity already exists"):
        import_dataset(db, dataset, owner.email, "collision", PASSWORD)
    assert existing.password_hash == "keep"


@database
def test_failure_rolls_back_entire_import(db, owner, dataset):
    with pytest.raises(RuntimeError, match="injected"), db.begin_nested():
        with patch(
            "app.services.dataset_import.persist_grouping", side_effect=RuntimeError("injected")
        ):
            import_dataset(db, dataset, owner.email, "rollback", PASSWORD)
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(Event)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@database
def test_signup_registration_and_grouping_include_a_new_member(client, db, owner, dataset):
    result = import_dataset(db, dataset, owner.email, "signup", PASSWORD)
    db.commit()
    response = client.post(
        "/auth/register",
        json={
            "name": "New member",
            "email": "new-college@example.com",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    person = response.json()["user"]["id"]
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    event = db.get(Event, result.event_ids["gfu-004"])
    with patch("app.services.registrations.utcnow", return_value=event.registration_opens_at):
        joined = client.post(f"/events/{event.id}/register")
    assert joined.status_code == 200, joined.text
    assert joined.json()["registration"]["status"] == "REGISTERED"
    as_user(client, db, owner)
    with patch("app.services.grouping.utcnow", return_value=event.grouping_at):
        preview = client.post(
            f"/events/{event.id}/grouping-runs",
            json={
                "request_id": str(uuid4()),
                "seed": 12,
            },
        )
    assert preview.status_code == 200, preview.text
    members = [m["user_id"] for team in preview.json()["teams"] for m in team["members"]]
    assert len(members) == len(set(members)) == 25 and person in members


@database
def test_explicit_shift_and_future_history_guard(db, owner, dataset):
    with patch("app.services.dataset_import.utcnow", return_value=NOW):
        result = import_dataset(db, dataset, owner.email, "shift", PASSWORD, shift_days=14)
        event = db.get(Event, result.event_ids["gfu-003"])
        source = next(e for e in dataset.events if e.id == "gfu-003")
        assert event.start_at == source.start_at + timedelta(days=14)
        with pytest.raises(ValueError, match="future"), db.begin_nested():
            import_dataset(db, dataset, owner.email, "future", PASSWORD, shift_days=365)
    assert db.scalar(select(func.count()).select_from(Event)) == 7


def test_cli_check_never_connects_or_prompts(monkeypatch, capsys):
    from app.import_college import main

    monkeypatch.setattr(
        "sys.argv", ["import_college", "--organizer", "owner@example.com", "--check"]
    )
    with (
        patch("app.import_college.make_engine") as engine,
        patch("app.import_college.getpass.getpass") as prompt,
    ):
        main()
    engine.assert_not_called()
    prompt.assert_not_called()
    assert "Validated 7 events and 80 source profiles" in capsys.readouterr().out


@pytest.mark.parametrize(
    "url", ["postgresql+psycopg://user@remote.example/db", "sqlite:///local.db"]
)
def test_cli_rejects_non_local_postgres(url, monkeypatch):
    from app.import_college import main

    monkeypatch.setattr("sys.argv", ["import_college", "--organizer", "owner@example.com"])
    monkeypatch.setenv("RAPO_DATABASE_URL", url)
    with patch("app.import_college.make_engine") as engine, pytest.raises(SystemExit):
        main()
    engine.assert_not_called()
