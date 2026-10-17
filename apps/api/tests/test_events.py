from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_auth import register

from app.models import AuditLog, User
from app.schemas.events import EventInput

pytestmark = pytest.mark.database


def event_body() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "title": "Community workshop",
        "description": "Meet new collaborators",
        "location": "Main hall",
        "timezone": "Asia/Kolkata",
        "start_at": (now + timedelta(days=10)).isoformat(),
        "end_at": (now + timedelta(days=10, hours=2)).isoformat(),
        "registration_opens_at": now.isoformat(),
        "registration_closes_at": (now + timedelta(days=5)).isoformat(),
        "confirmation_deadline": (now + timedelta(days=9)).isoformat(),
        "capacity": 40,
        "min_team_size": 3,
        "max_team_size": 5,
    }


def make_organizer(client: TestClient, db: Session, email: str = "owner@example.com") -> None:
    register(client, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = "organizer"
    db.commit()


def test_full_event_lifecycle_and_audit(client: TestClient, db: Session) -> None:
    make_organizer(client, db)
    response = client.post("/events", json=event_body())
    assert response.status_code == 201, response.text
    event = response.json()
    event_id = event["id"]
    assert event["status"] == "DRAFT"
    assert client.get("/events").json()["total"] == 0
    assert client.get(f"/events/{event_id}").status_code == 404
    assert len(client.get("/organizer/events").json()) == 1
    updated = client.patch(f"/events/{event_id}", json={"title": "Fresh teams", "version": 1})
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert client.post(f"/events/{event_id}/publish", json={"version": 1}).status_code == 409
    published = client.post(f"/events/{event_id}/publish", json={"version": 2})
    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"
    assert client.get("/events").json()["items"][0]["title"] == "Fresh teams"
    assert client.get(f"/events/{event_id}").status_code == 200
    assert (
        client.patch(f"/events/{event_id}", json={"title": "No", "version": 3}).status_code == 409
    )
    assert client.post(f"/events/{event_id}/cancel", json={"version": 3}).status_code == 200
    assert client.get(f"/events/{event_id}").status_code == 404
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 4


def test_participant_cannot_manage_events(client: TestClient) -> None:
    assert client.post("/events", json=event_body()).status_code == 401
    register(client)
    assert client.post("/events", json=event_body()).status_code == 403
    assert client.get("/organizer/events").status_code == 403


def test_other_organizer_cannot_read_or_modify_draft(client: TestClient, db: Session) -> None:
    make_organizer(client, db)
    event_id = client.post("/events", json=event_body()).json()["id"]
    make_organizer(client, db, "other@example.com")
    assert client.get(f"/organizer/events/{event_id}").status_code == 404
    assert client.get(f"/events/{event_id}").status_code == 404
    assert (
        client.patch(f"/events/{event_id}", json={"title": "Stolen", "version": 1}).status_code
        == 404
    )
    assert client.post(f"/events/{event_id}/publish", json={"version": 1}).status_code == 404
    assert client.post(f"/events/{event_id}/cancel", json={"version": 1}).status_code == 404


@pytest.mark.parametrize(
    "update",
    [
        {"timezone": "Not/AZone"},
        {"min_team_size": 6},
        {"capacity": 2},
        {"start_at": "2030-01-01T10:00:00"},
        {"registration_closes_at": "2000-01-01T00:00:00Z"},
        {"organizer_id": "00000000-0000-0000-0000-000000000001"},
    ],
)
def test_invalid_event_configuration(
    client: TestClient, db: Session, update: dict[str, object]
) -> None:
    make_organizer(client, db)
    assert client.post("/events", json=event_body() | update).status_code == 422


def test_patch_validation_and_stale_edits(client: TestClient, db: Session) -> None:
    make_organizer(client, db)
    event_id = client.post("/events", json=event_body()).json()["id"]
    assert (
        client.patch(f"/events/{event_id}", json={"title": None, "version": 1}).status_code == 422
    )
    assert (
        client.patch(f"/events/{event_id}", json={"min_team_size": 10, "version": 1}).status_code
        == 422
    )
    assert (
        client.patch(f"/events/{event_id}", json={"capacity": None, "version": 1}).status_code
        == 200
    )
    assert (
        client.patch(f"/events/{event_id}", json={"title": "Stale", "version": 1}).status_code
        == 409
    )


def test_grouping_defaults_wait_for_late_registration_close() -> None:
    body = event_body()
    body["registration_closes_at"] = (datetime.now(UTC) + timedelta(days=8)).isoformat()
    event = EventInput.model_validate(body)
    assert event.grouping_at == event.registration_closes_at


def test_public_pagination_and_private_status_filter(client: TestClient, db: Session) -> None:
    make_organizer(client, db)
    for _ in range(2):
        event_id = client.post("/events", json=event_body()).json()["id"]
        assert client.post(f"/events/{event_id}/publish", json={"version": 1}).status_code == 200
    page = client.get("/events?limit=1&offset=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get("/events?status=DRAFT").status_code == 422
    assert client.get("/events?date_from=2100-01-01").json()["total"] == 0


@pytest.mark.parametrize("sort", ["soonest", "latest", "title"])
def test_sorting_is_stable_before_pagination_and_combines_with_filters(
    client: TestClient, db: Session, sort: str
) -> None:
    make_organizer(client, db)
    events = []
    base = datetime.now(UTC)
    for days, title in [(12, "Zebra"), (10, "beta"), (11, "Alpha"), (11, "alpha")]:
        body = event_body() | {
            "title": title,
            "start_at": (base + timedelta(days=days)).isoformat(),
            "end_at": (base + timedelta(days=days, hours=2)).isoformat(),
        }
        event = client.post("/events", json=body).json()
        assert client.post(f"/events/{event['id']}/publish", json={"version": 1}).status_code == 200
        events.append(event)
    # A draft cannot enter the public listing through any sort option.
    client.post("/events", json=event_body() | {"title": "AAA private draft"})

    def order(event):
        if sort == "title":
            return event["title"].lower(), event["id"]
        timestamp = datetime.fromisoformat(event["start_at"]).timestamp()
        return (-timestamp if sort == "latest" else timestamp), event["id"]

    expected = sorted(events, key=order)
    page = client.get(f"/events?sort={sort}&offset=1&limit=2").json()
    assert page["total"] == 4
    assert [event["id"] for event in page["items"]] == [e["id"] for e in expected[1:3]]
    day = (base + timedelta(days=11)).date().isoformat()
    filtered = client.get(
        f"/events?sort={sort}&date_from={day}&date_to={day}&status=PUBLISHED"
    ).json()
    assert filtered["total"] == 2
    assert [event["id"] for event in filtered["items"]] == [
        event["id"] for event in expected if event["title"].lower() == "alpha"
    ]
    assert client.get(f"/events?sort={sort}&date_to=9999-12-31").json()["total"] == 4


def test_invalid_sort_is_rejected(client: TestClient) -> None:
    assert client.get("/events?sort=unknown").status_code == 422
