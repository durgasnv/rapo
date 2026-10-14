from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy import event as sql_event
from test_auth import register
from test_events import event_body, make_organizer

from app.models import AuditLog, Event, User, utcnow

pytestmark = pytest.mark.database


@pytest.fixture
def audit_event(client, db):
    make_organizer(client, db)
    response = client.post("/events", json=event_body())
    assert response.status_code == 201
    return db.get(Event, UUID(response.json()["id"]))


def read(client, event, **params):
    response = client.get(f"/organizer/events/{event.id}/audit", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_audit_requires_owner_and_organizer(client, db, audit_event):
    path = f"/organizer/events/{audit_event.id}/audit"
    client.cookies.clear()
    assert client.get(path).status_code == 401
    register(client, "participant@example.com")
    assert client.get(path).status_code == 403
    make_organizer(client, db, "other-owner@example.com")
    assert client.get(path).status_code == 404
    assert client.get(f"/organizer/events/{uuid4()}/audit").status_code == 404


@pytest.mark.parametrize("params", [{"offset": -1}, {"limit": 0}, {"limit": 101}])
def test_audit_pagination_validation(client, audit_event, params):
    assert client.get(f"/organizer/events/{audit_event.id}/audit", params=params).status_code == 422


def test_audit_private_projection_and_system_actor(client, db, audit_event):
    owner = db.get(User, audit_event.organizer_id)
    entries = [
        AuditLog(
            event_id=audit_event.id,
            actor_id=owner.id,
            action=action,
            before_json={"secret": "private-before", "email": "private@example.com"},
            after_json={"members": ["private-member-id"], "secret": "private-after"},
        )
        for action in [
            "teams.reassigned",
            "grouping.scheduled",
            "demo.seeded",
            "internal-secret-action",
        ]
    ]
    db.add_all(entries)
    db.commit()
    items = {item["id"]: item for item in read(client, audit_event)["items"]}
    human, worker, demo, unknown = [items[str(row.id)] for row in entries]
    assert human["description"] == "Team members reassigned" and human["actor_name"] == owner.name
    assert (
        worker["description"] == "Scheduled grouping preview generated"
        and worker["actor_name"] == "Scheduled worker"
    )
    assert demo["actor_name"] == "Demo setup"
    assert unknown["description"] == "Other event activity" and unknown["action"] == "other"
    for item in items.values():
        assert set(item) == {"id", "action", "description", "actor_name", "created_at"}
    text = str(items)
    assert all(
        value not in text
        for value in [
            "private-before",
            "private-after",
            "private-member-id",
            "private@example.com",
            owner.email,
            "internal-secret-action",
        ]
    )
    owner.name = "Updated organizer name"
    db.commit()
    updated = {item["id"]: item for item in read(client, audit_event)["items"]}
    assert updated[str(entries[0].id)]["actor_name"] == owner.name
    assert updated[str(entries[1].id)]["actor_name"] == "Scheduled worker"


def test_audit_stable_pagination_and_joined_actor_query(client, db, connection, audit_event):
    now = utcnow()
    db.add_all(
        [
            AuditLog(
                id=UUID(int=i),
                event_id=audit_event.id,
                actor_id=audit_event.organizer_id,
                action="event.updated",
                created_at=now,
            )
            for i in range(1, 26)
        ]
    )
    db.commit()
    # Read audit joins actors in one query, even with many entries on the page.
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    # Resolve the fixture's expired attributes before recording the API's own queries.
    event_id = audit_event.id
    sql_event.listen(connection, "before_cursor_execute", record)
    try:
        first = client.get(f"/organizer/events/{event_id}/audit?limit=20").json()
        count = len(statements)
        statements.clear()
        second = client.get(f"/organizer/events/{event_id}/audit?offset=20&limit=20").json()
        assert len(statements) == count == 5  # auth (2), ownership (1), total and page (2)
    finally:
        sql_event.remove(connection, "before_cursor_execute", record)
    assert first["total"] == second["total"] == 26
    assert [item["id"] for item in first["items"]] == [str(UUID(int=i)) for i in range(25, 5, -1)]
    assert [item["id"] for item in second["items"][:5]] == [
        str(UUID(int=i)) for i in range(5, 0, -1)
    ]
    assert len(second["items"]) == 6
    assert {item["id"] for item in first["items"]}.isdisjoint(
        {item["id"] for item in second["items"]}
    )
    assert read(client, audit_event, offset=100)["items"] == []


def test_audit_is_scoped_and_read_only(client, db, audit_event):
    other = client.post("/events", json=event_body()).json()
    db.add(
        AuditLog(
            event_id=UUID(other["id"]), actor_id=audit_event.organizer_id, action="event.cancelled"
        )
    )
    db.commit()
    before = db.scalar(select(func.count()).select_from(AuditLog))
    version = audit_event.version
    assert [item["action"] for item in read(client, audit_event)["items"]] == ["event.created"]
    assert client.post(f"/organizer/events/{audit_event.id}/audit").status_code == 405
    assert db.scalar(select(func.count()).select_from(AuditLog)) == before
    db.refresh(audit_event)
    assert audit_event.version == version


@pytest.mark.parametrize("status", ["DRAFT", "CANCELLED", "COMPLETED", "IN_PROGRESS"])
def test_audit_retained_in_all_owned_event_states(client, db, audit_event, status):
    audit_event.status = status
    db.commit()
    assert read(client, audit_event)["total"] == 1


def test_audit_empty_legacy_event(client, db, audit_event):
    db.execute(delete(AuditLog).where(AuditLog.event_id == audit_event.id))
    db.commit()
    assert read(client, audit_event) == {"items": [], "total": 0, "offset": 0, "limit": 20}
