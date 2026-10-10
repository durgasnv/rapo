from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth import PASSWORD, register
from test_events import event_body, make_organizer

from app.core.config import Settings
from app.main import create_app
from app.models import AuditLog, Event, LoginSession, Registration, User, utcnow
from app.schemas.events import EventInput
from app.security import COOKIE_NAME, token_hash

pytestmark = pytest.mark.database


def published_event(client: TestClient, db: Session, capacity: int | None = 1) -> UUID:
    make_organizer(client, db)
    response = client.post(
        "/events",
        json=event_body() | {"capacity": capacity, "min_team_size": 1, "max_team_size": 2},
    )
    assert response.status_code == 201, response.text
    event_id = UUID(response.json()["id"])
    assert client.post(f"/events/{event_id}/publish", json={"version": 1}).status_code == 200
    return event_id


def login(client: TestClient, email: str) -> None:
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def join(client: TestClient, event_id: UUID) -> dict:
    response = client.post(f"/events/{event_id}/register")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_capacity_fifo_promotion_and_dashboard(client: TestClient, db: Session) -> None:
    event_id = published_event(client, db)
    register(client, "first@example.com")
    first = join(client, event_id)
    assert first["registered_count"] == 1
    assert first["registration"]["status"] == "REGISTERED"
    assert first["registration"]["waitlist_position"] is None
    assert join(client, event_id) == first
    register(client, "second@example.com")
    second = join(client, event_id)
    assert second["registration"]["status"] == "WAITLISTED"
    assert second["registration"]["waitlist_position"] == 1
    register(client, "third@example.com")
    assert join(client, event_id)["registration"]["waitlist_position"] == 2
    page = client.get("/me/registrations?limit=1").json()
    assert page["total"] == 1
    assert page["items"][0]["event"]["id"] == str(event_id)
    assert page["items"][0]["waitlist_position"] == 2
    assert client.get("/me/registrations?offset=1").json()["items"] == []
    login(client, "first@example.com")
    response = client.delete(f"/events/{event_id}/registration")
    assert response.status_code == 200
    assert response.json()["registration"]["status"] == "CANCELLED"
    assert response.json()["registered_count"] == 1
    assert response.json()["waitlisted_count"] == 1
    assert client.delete(f"/events/{event_id}/registration").json() == response.json()
    # Rejoining keeps the unique row, but goes behind the remaining waitlisted person.
    rejoined = join(client, event_id)
    assert rejoined["registration"]["id"] == first["registration"]["id"]
    assert rejoined["registration"]["waitlist_position"] == 2
    login(client, "second@example.com")
    assert (
        client.get(f"/events/{event_id}/registration").json()["registration"]["status"]
        == "REGISTERED"
    )
    assert client.delete(f"/events/{event_id}/registration").status_code == 200
    login(client, "third@example.com")
    assert (
        client.get(f"/events/{event_id}/registration").json()["registration"]["status"]
        == "REGISTERED"
    )
    assert db.scalar(select(func.count()).select_from(Registration)) == 3


def test_waitlisted_withdrawal_compacts_positions_without_using_a_seat(
    client: TestClient, db: Session
) -> None:
    event_id = published_event(client, db)
    register(client, "seat@example.com")
    join(client, event_id)
    register(client, "waiting@example.com")
    join(client, event_id)
    register(client, "last@example.com")
    join(client, event_id)
    login(client, "waiting@example.com")
    result = client.delete(f"/events/{event_id}/registration").json()
    assert result["registered_count"] == 1 and result["waitlisted_count"] == 1
    login(client, "last@example.com")
    assert (
        client.get(f"/events/{event_id}/registration").json()["registration"]["waitlist_position"]
        == 1
    )


def test_unlimited_capacity_never_waitlists(client: TestClient, db: Session) -> None:
    event_id = published_event(client, db, capacity=None)
    for index in range(3):
        register(client, f"uncapped-{index}@example.com")
        result = join(client, event_id)
        assert result["capacity"] is None
        assert result["registration"]["status"] == "REGISTERED"
        assert result["waitlisted_count"] == 0
    assert result["registered_count"] == 3
    assert client.delete(f"/events/{event_id}/registration").json()["registered_count"] == 2


def test_registration_windows_and_promotion_after_close(client: TestClient, db: Session) -> None:
    event_id = published_event(client, db)
    register(client, "seat@example.com")
    first = join(client, event_id)
    register(client, "waiting@example.com")
    join(client, event_id)
    event = db.get(Event, event_id)
    assert event is not None
    event.registration_opens_at = utcnow() - timedelta(days=2)
    event.registration_closes_at = utcnow() - timedelta(days=1)
    db.commit()
    register(client, "late@example.com")
    assert client.post(f"/events/{event_id}/register").status_code == 409
    state = client.get(f"/events/{event_id}/registration").json()
    assert not state["registration_open"] and state["withdrawal_open"]
    login(client, "seat@example.com")
    assert join(client, event_id)["registration"]["id"] == first["registration"]["id"]
    assert client.delete(f"/events/{event_id}/registration").status_code == 200
    login(client, "waiting@example.com")
    assert (
        client.get(f"/events/{event_id}/registration").json()["registration"]["status"]
        == "REGISTERED"
    )
    event.grouping_at = utcnow() - timedelta(hours=1)
    db.commit()
    assert client.delete(f"/events/{event_id}/registration").status_code == 409
    assert not client.get(f"/events/{event_id}/registration").json()["withdrawal_open"]


def test_not_open_yet_and_drafts_are_not_joinable(client: TestClient, db: Session) -> None:
    event_id = published_event(client, db)
    event = db.get(Event, event_id)
    assert event is not None
    event.registration_opens_at = utcnow() + timedelta(days=1)
    db.commit()
    register(client)
    assert client.post(f"/events/{event_id}/register").status_code == 409
    event.status = "DRAFT"
    db.commit()
    assert client.post(f"/events/{event_id}/register").status_code == 404
    assert client.get(f"/events/{event_id}/registration").status_code == 404
    assert client.delete(f"/events/{event_id}/registration").status_code == 404
    assert client.post(f"/events/{uuid4()}/register").status_code == 404


def test_exact_registration_and_withdrawal_boundaries(client: TestClient, db: Session) -> None:
    event_id = published_event(client, db)
    event = db.get(Event, event_id)
    assert event is not None
    register(client, "boundary-first@example.com")
    with patch(
        "app.services.registrations.utcnow",
        return_value=event.registration_opens_at - timedelta(microseconds=1),
    ):
        assert client.post(f"/events/{event_id}/register").status_code == 409
    with patch("app.services.registrations.utcnow", return_value=event.registration_opens_at):
        assert join(client, event_id)["registration"]["status"] == "REGISTERED"
    register(client, "boundary-second@example.com")
    with patch("app.services.registrations.utcnow", return_value=event.registration_closes_at):
        assert client.post(f"/events/{event_id}/register").status_code == 409
    with patch(
        "app.services.registrations.utcnow",
        return_value=event.registration_closes_at - timedelta(microseconds=1),
    ):
        assert join(client, event_id)["registration"]["status"] == "WAITLISTED"
    login(client, "boundary-first@example.com")
    with patch("app.services.registrations.utcnow", return_value=event.grouping_at):
        assert client.delete(f"/events/{event_id}/registration").status_code == 409
    with patch(
        "app.services.registrations.utcnow",
        return_value=event.grouping_at - timedelta(microseconds=1),
    ):
        assert client.delete(f"/events/{event_id}/registration").json()["registered_count"] == 1


def test_registration_privacy_authorization_and_delete_cors(
    client: TestClient, db: Session
) -> None:
    event_id = published_event(client, db)
    participant = register(client, "participant@example.com")
    join(client, event_id)
    assert client.get(f"/events/{event_id}/registrations").status_code == 403
    assert client.get("/me/registrations").headers["cache-control"] == "no-store"
    assert client.get("/me/registrations?limit=101").status_code == 422
    assert (
        client.post(f"/events/{event_id}/register", headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert (
        client.delete(
            f"/events/{event_id}/registration", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    preflight = client.options(
        f"/events/{event_id}/registration",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "x-csrf-token",
        },
    )
    assert preflight.status_code == 200
    register(client, "other@example.com")
    # A client-supplied user ID cannot register or cancel somebody else.
    result = client.post(
        f"/events/{event_id}/register",
        json={"user_id": participant["user"]["id"], "status": "REGISTERED"},
    )
    assert result.json()["registration"]["status"] == "WAITLISTED"
    assert client.delete(f"/events/{event_id}/registration").status_code == 200
    make_organizer(client, db, "intruder@example.com")
    assert client.get(f"/events/{event_id}/registrations").status_code == 404
    login(client, "owner@example.com")
    roster = client.get(f"/events/{event_id}/registrations?limit=1")
    assert roster.status_code == 200 and roster.headers["cache-control"] == "no-store"
    assert roster.json()["total"] == 2
    assert roster.json()["items"][0]["status"] == "REGISTERED"
    assert "email" not in roster.text and "password" not in roster.text
    client.cookies.clear()
    for method, path in [
        ("GET", "/me/registrations"),
        ("GET", f"/events/{event_id}/registration"),
        ("POST", f"/events/{event_id}/register"),
        ("DELETE", f"/events/{event_id}/registration"),
    ]:
        response = client.request(method, path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"


def test_event_cancellation_is_visible_to_existing_participants(
    client: TestClient, db: Session
) -> None:
    event_id = published_event(client, db)
    register(client)
    join(client, event_id)
    login(client, "owner@example.com")
    event = client.get(f"/organizer/events/{event_id}").json()
    assert (
        client.post(f"/events/{event_id}/cancel", json={"version": event["version"]}).status_code
        == 200
    )
    login(client, "person@example.com")
    dashboard = client.get("/me/registrations").json()
    assert dashboard["items"][0]["event"]["status"] == "CANCELLED"
    state = client.get(f"/events/{event_id}/registration").json()
    assert state["event_status"] == "CANCELLED"
    assert not state["registration_open"] and not state["withdrawal_open"]
    assert client.post(f"/events/{event_id}/register").status_code == 404
    assert client.delete(f"/events/{event_id}/registration").status_code == 409
    assert db.scalar(select(func.count()).select_from(Registration)) == 1


def test_failed_withdrawal_rolls_back_promotion(client: TestClient, db: Session) -> None:
    event_id = published_event(client, db)
    register(client, "seat@example.com")
    join(client, event_id)
    register(client, "waiting@example.com")
    join(client, event_id)
    login(client, "seat@example.com")
    with patch("app.services.registrations.state", side_effect=RuntimeError("response failure")):
        with pytest.raises(RuntimeError, match="response failure"):
            client.delete(f"/events/{event_id}/registration")
    statuses = db.scalars(select(Registration.status).order_by(Registration.queue_number)).all()
    assert statuses == ["REGISTERED", "WAITLISTED"]
    assert client.delete(f"/events/{event_id}/registration").json()["registered_count"] == 1


def test_registration_database_constraints(client: TestClient, db: Session) -> None:
    event_id = published_event(client, db)
    register(client)
    own = join(client, event_id)["registration"]
    saved = db.get(Registration, UUID(own["id"]))
    assert saved is not None
    other = register(client, "constraint-other@example.com")
    other_id = UUID(other["user"]["id"])
    for updates, constraint in [
        ({"queue_number": 2}, "registration_event_user"),
        ({"user_id": other_id}, "registration_queue_number"),
        ({"status": "INVALID", "user_id": other_id, "queue_number": 2}, "registration_status"),
        ({"queue_number": 0, "user_id": other_id}, "registration_queue_positive"),
    ]:
        with pytest.raises(IntegrityError) as error, db.begin_nested():
            values = {
                "event_id": event_id,
                "user_id": saved.user_id,
                "status": "REGISTERED",
                "queue_number": 1,
            } | updates
            db.add(Registration(**values))
            db.flush()
        assert error.value.orig.diag.constraint_name == constraint


@pytest.fixture
def race_setup(database_engine: Engine) -> Iterator[tuple[FastAPI, UUID, list[str]]]:
    users = [
        User(
            name=f"Racer {index}",
            email=f"{uuid4()}@example.com",
            password_hash="unused",
            role="participant",
        )
        for index in range(4)
    ]
    tokens = [str(uuid4()) for _ in users]
    with Session(database_engine) as db:
        db.add_all(users)
        db.flush()
        user_ids = [user.id for user in users]
        event = Event(
            **EventInput.model_validate(
                event_body() | {"capacity": 1, "min_team_size": 1}
            ).model_dump(),
            organizer_id=user_ids[0],
            status="PUBLISHED",
        )
        db.add(event)
        db.flush()
        event_id = event.id
        db.add_all(
            [
                LoginSession(
                    token_hash=token_hash(token),
                    user_id=user_id,
                    csrf_token="race-csrf",
                    expires_at=utcnow() + timedelta(hours=1),
                )
                for token, user_id in zip(tokens, user_ids, strict=True)
            ]
        )
        db.commit()
    application = create_app(Settings())
    application.state.engine = database_engine
    try:
        yield application, event_id, tokens
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(AuditLog).where(AuditLog.event_id == event_id))
            connection.execute(delete(Registration).where(Registration.event_id == event_id))
            connection.execute(delete(Event).where(Event.id == event_id))
            connection.execute(delete(LoginSession).where(LoginSession.user_id.in_(user_ids)))
            connection.execute(delete(User).where(User.id.in_(user_ids)))


def race_request(
    application: FastAPI, event_id: UUID, token: str, method: str, barrier: Barrier | None = None
) -> dict:
    with TestClient(application, base_url="http://127.0.0.1:8000") as client:
        client.cookies.set(COOKIE_NAME, token)
        client.headers["X-CSRF-Token"] = "race-csrf"
        if barrier:
            barrier.wait(timeout=10)
        suffix = "register" if method == "POST" else "registration"
        response = client.request(method, f"/events/{event_id}/{suffix}")
        assert response.status_code == 200, response.text
        return response.json()


def test_concurrent_last_seat(
    race_setup: tuple[FastAPI, UUID, list[str]], database_engine: Engine
) -> None:
    app, event_id, tokens = race_setup
    barrier = Barrier(4)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(race_request, app, event_id, token, "POST", barrier) for token in tokens
        ]
        statuses = [future.result(timeout=30)["registration"]["status"] for future in futures]
    assert statuses.count("REGISTERED") == 1 and statuses.count("WAITLISTED") == 3
    with Session(database_engine) as db:
        rows = db.scalars(
            select(Registration)
            .where(Registration.event_id == event_id)
            .order_by(Registration.queue_number)
        ).all()
        assert [row.queue_number for row in rows] == [1, 2, 3, 4]
        assert [row.status for row in rows] == [
            "REGISTERED",
            "WAITLISTED",
            "WAITLISTED",
            "WAITLISTED",
        ]


def test_concurrent_duplicate_requests(
    race_setup: tuple[FastAPI, UUID, list[str]], database_engine: Engine
) -> None:
    app, event_id, tokens = race_setup
    barrier = Barrier(4)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(race_request, app, event_id, tokens[0], "POST", barrier) for _ in range(4)
        ]
        ids = [future.result(timeout=30)["registration"]["id"] for future in futures]
    assert len(set(ids)) == 1
    with Session(database_engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Registration)
                .where(Registration.event_id == event_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.event_id == event_id)
            )
            == 1
        )


@pytest.mark.parametrize(
    "other_action", ["new_join", "duplicate_withdrawal", "waitlist_withdrawal"]
)
def test_concurrent_withdrawal_and_promotion(
    race_setup: tuple[FastAPI, UUID, list[str]], database_engine: Engine, other_action: str
) -> None:
    app, event_id, tokens = race_setup
    for token in tokens[:3]:
        race_request(app, event_id, token, "POST")
    other_token, method = {
        "new_join": (tokens[3], "POST"),
        "duplicate_withdrawal": (tokens[0], "DELETE"),
        "waitlist_withdrawal": (tokens[1], "DELETE"),
    }[other_action]
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(race_request, app, event_id, token, action, barrier)
            for token, action in [(tokens[0], "DELETE"), (other_token, method)]
        ]
        for future in futures:
            future.result(timeout=30)
    with Session(database_engine) as db:
        rows = db.scalars(
            select(Registration)
            .where(Registration.event_id == event_id)
            .order_by(Registration.queue_number)
        ).all()
        assert sum(row.status == "REGISTERED" for row in rows) == 1
        assert rows[0].status == "CANCELLED"
        if other_action == "waitlist_withdrawal":
            assert rows[1].status == "CANCELLED" and rows[2].status == "REGISTERED"
        else:
            assert rows[1].status == "REGISTERED" and rows[2].status == "WAITLISTED"
        if other_action == "new_join":
            assert rows[3].status == "WAITLISTED"
