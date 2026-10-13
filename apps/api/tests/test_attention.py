from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import event as sql_event
from sqlalchemy import func, select
from test_auth import register
from test_events import event_body, make_organizer
from test_grouping import grouping_event  # noqa: F401 -- injected fixture
from test_teams import finalized  # noqa: F401 -- injected fixture

from app.models import Assignment, AuditLog, Event, GroupingJob, Notification, User, utcnow
from app.schemas.events import EventInput

pytestmark = pytest.mark.database


def add_event(db, owner, status="GROUPS_PROPOSED", **values):
    row = Event(
        **EventInput.model_validate(event_body() | values).model_dump(),
        organizer_id=owner.id,
        status=status,
    )
    db.add(row)
    db.flush()
    return row


def overview(client, **params):
    response = client.get("/organizer/attention", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_attention_auth_and_empty_state(client, db):
    assert client.get("/organizer/attention").status_code == 401
    register(client)
    assert client.get("/organizer/attention").status_code == 403
    make_organizer(client, db)
    assert overview(client) == {"items": [], "total": 0, "offset": 0, "limit": 20}


@pytest.mark.parametrize("query", [{"offset": -1}, {"limit": 0}, {"limit": 101}])
def test_attention_validates_pagination(client, db, query):
    make_organizer(client, db)
    assert client.get("/organizer/attention", params=query).status_code == 422


def test_attention_jobs_previews_terminal_states_and_privacy(client, db):
    make_organizer(client, db)
    owner = db.scalar(select(User).where(User.email == "owner@example.com"))
    failed = add_event(db, owner, "PUBLISHED", title="Failed event")
    blocked = add_event(db, owner, "PUBLISHED", title="Blocked event")
    preview = add_event(db, owner, title="Preview event")
    for row in [failed, blocked, preview]:
        db.add(
            GroupingJob(
                event_id=row.id,
                status="BLOCKED" if row == blocked else "FAILED",
                attempts=1,
                code="test",
                message="Private diagnostic",
                next_attempt_at=utcnow(),
            )
        )
    for status in ["DRAFT", "COMPLETED", "CANCELLED", "IN_PROGRESS"]:
        row = add_event(db, owner, status)
        db.add(
            GroupingJob(
                event_id=row.id,
                status="FAILED",
                attempts=1,
                code="test",
                message="Old diagnostic",
                next_attempt_at=utcnow(),
            )
        )
    add_event(db, owner, "PUBLISHED", title="Waiting event")
    outsider = User(
        name="Other organizer",
        email="other-owner@example.com",
        password_hash="unused",
        role="organizer",
    )
    db.add(outsider)
    db.flush()
    add_event(db, outsider, title="Other organizer secret")
    db.commit()
    before = (
        db.scalar(select(func.count()).select_from(AuditLog)),
        db.scalar(select(func.count()).select_from(Notification)),
    )
    result = overview(client)
    assert result["total"] == 3
    reasons = {item["title"]: item["reasons"] for item in result["items"]}
    assert reasons == {
        "Failed event": ["Grouping failed. Review the job details."],
        "Blocked event": ["Grouping blocked. Review feasibility and job details."],
        "Preview event": ["Preview awaiting review."],
    }
    assert set(result["items"][0]) == {
        "event_id",
        "title",
        "start_at",
        "timezone",
        "status",
        "reasons",
    }
    assert "Private diagnostic" not in str(result) and "@example.com" not in str(result)
    assert "Other organizer secret" not in str(result)
    assert before == (
        db.scalar(select(func.count()).select_from(AuditLog)),
        db.scalar(select(func.count()).select_from(Notification)),
    )


def test_attention_pages_past_100_events_and_has_constant_query_count(client, db, connection):
    make_organizer(client, db)
    owner = db.scalar(select(User).where(User.email == "owner@example.com"))
    for index in range(105):
        add_event(db, owner, title=f"Review {index}")
    db.commit()
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    sql_event.listen(connection, "before_cursor_execute", record)
    try:
        first = overview(client, limit=100)
        first_queries = len(statements)
        statements.clear()
        last = overview(client, offset=100, limit=100)
        assert len(statements) == first_queries == 4  # two auth reads + count + page
    finally:
        sql_event.remove(connection, "before_cursor_execute", record)
    assert first["total"] == last["total"] == 105
    assert len(first["items"]) == 100 and len(last["items"]) == 5
    assert {item["event_id"] for item in first["items"]}.isdisjoint(
        {item["event_id"] for item in last["items"]}
    )
    assert overview(client, offset=200)["items"] == []


def test_attention_tracks_roster_issues_and_resolved_vacancy(client, db, finalized):  # noqa: F811
    event, _, _, initial = finalized
    assert overview(client)["total"] == 0  # pending members are not overdue yet
    rows = list(db.scalars(select(Assignment).where(Assignment.event_id == event.id)))
    rows[0].status = "WITHDRAWN"
    db.commit()
    assert overview(client)["items"][0]["reasons"] == [
        "Below minimum: 1 team.",
        "Vacancy: 1 unfilled place.",
    ]
    rows[0].status = "DECLINED"
    db.commit()
    assert overview(client)["items"][0]["reasons"] == [
        "Below minimum: 1 team.",
        "Vacancy: 1 unfilled place.",
    ]
    # A retained failed job must not override the finalized roster's current state.
    db.add(
        GroupingJob(
            event_id=event.id,
            status="FAILED",
            attempts=1,
            code="old",
            message="Old failure",
            next_attempt_at=utcnow(),
        )
    )
    rows[0].status = "CONFIRMED"
    db.commit()
    assert overview(client)["total"] == 0
    event.grouping_at = event.registration_closes_at
    event.confirmation_deadline = utcnow() - timedelta(hours=1)
    db.commit()
    assert overview(client)["items"][0]["reasons"] == ["Confirmation overdue: 5 members."]
    for row in rows:
        row.status = "WITHDRAWN"
    db.commit()
    assert overview(client)["items"][0]["reasons"] == [
        "Below minimum: 3 teams.",
        "Vacancy: 6 unfilled places.",
    ]
    event.status = "COMPLETED"
    db.commit()
    assert overview(client)["total"] == 0


def test_attention_deadline_boundary_matches_team_roster(client, db, finalized):  # noqa: F811
    event, *_ = finalized
    with patch("app.services.attention.utcnow", return_value=event.confirmation_deadline):
        assert overview(client)["items"][0]["reasons"] == ["Confirmation overdue: 6 members."]
    with patch("app.services.teams.utcnow", return_value=event.confirmation_deadline):
        roster = client.get(f"/events/{event.id}/teams").json()
        assert sum(team["status"] == "NEEDS_ATTENTION" for team in roster["teams"]) == 3


def test_attention_above_maximum(client, db, finalized):  # noqa: F811
    event, *_ = finalized
    event.min_team_size = event.max_team_size = 1
    db.commit()
    assert overview(client)["items"][0]["reasons"] == ["Above maximum: 3 teams."]
