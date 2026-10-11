"""In-process API contention check; not a network/production load benchmark."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from math import ceil
from statistics import median
from threading import Event as StartGate
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_registrations import race_request

from app.core.config import Settings
from app.main import create_app
from app.models import AuditLog, Event, LoginSession, Registration, User, utcnow
from app.security import token_hash

pytestmark = pytest.mark.database


def test_120_registration_requests_with_16_workers(database_engine: Engine) -> None:
    now = utcnow()
    users = [
        User(
            name=f"Load member {n}",
            email=f"{uuid4()}@example.com",
            password_hash="unused",
            role="participant",
        )
        for n in range(120)
    ]
    tokens = [str(uuid4()) for _ in users]
    with Session(database_engine) as db, db.begin():
        db.add_all(users)
        db.flush()
        ids = [user.id for user in users]
        event = Event(
            organizer_id=ids[0],
            title="Isolated registration load test",
            description="Synthetic",
            timezone="UTC",
            start_at=now + timedelta(days=7),
            end_at=now + timedelta(days=8),
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=1),
            grouping_at=now + timedelta(days=2),
            confirmation_deadline=now + timedelta(days=5),
            capacity=100,
            min_team_size=3,
            max_team_size=5,
            status="PUBLISHED",
        )
        db.add(event)
        db.flush()
        event_id = event.id
        db.add_all(
            LoginSession(
                token_hash=token_hash(token),
                user_id=user_id,
                csrf_token="race-csrf",
                expires_at=now + timedelta(hours=1),
            )
            for token, user_id in zip(tokens, ids, strict=True)
        )
    app = create_app(Settings())
    app.state.engine = database_engine
    gate = StartGate()

    def request(token: str) -> tuple[str, float]:
        assert gate.wait(timeout=30)
        start = perf_counter()
        response = race_request(app, event_id, token, "POST")
        return response["registration"]["status"], perf_counter() - start

    try:
        start = perf_counter()
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(request, token) for token in tokens]
            gate.set()
            results = [future.result(timeout=60) for future in futures]
        elapsed = perf_counter() - start
        statuses = [status for status, _ in results]
        assert statuses.count("REGISTERED") == 100 and statuses.count("WAITLISTED") == 20
        timings = sorted(duration for _, duration in results)
        print(
            f"120 registrations / 16 workers: total={elapsed:.3f}s; "
            f"median={median(timings):.3f}s; p95={timings[ceil(len(timings) * 0.95) - 1]:.3f}s; "
            f"max={timings[-1]:.3f}s"
        )
        with Session(database_engine) as db:
            rows = list(
                db.scalars(
                    select(Registration)
                    .where(Registration.event_id == event_id)
                    .order_by(Registration.queue_number)
                )
            )
            assert len(rows) == len({row.user_id for row in rows}) == 120
            assert [row.queue_number for row in rows] == list(range(1, 121))
            assert [row.status for row in rows] == ["REGISTERED"] * 100 + ["WAITLISTED"] * 20
        # Retrying every request cannot consume another seat or queue ticket.
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(lambda token: race_request(app, event_id, token, "POST"), tokens))
        with Session(database_engine) as db:
            rows = list(db.scalars(select(Registration).where(Registration.event_id == event_id)))
            assert len(rows) == 120 and sum(row.status == "REGISTERED" for row in rows) == 100
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(AuditLog).where(AuditLog.event_id == event_id))
            connection.execute(delete(Registration).where(Registration.event_id == event_id))
            connection.execute(delete(Event).where(Event.id == event_id))
            connection.execute(delete(LoginSession).where(LoginSession.user_id.in_(ids)))
            connection.execute(delete(User).where(User.id.in_(ids)))
