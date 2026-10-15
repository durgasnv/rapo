import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta
from threading import Barrier
from threading import Event as ThreadEvent
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import event as sql_event
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_auth import PASSWORD, register
from test_registrations import race_setup  # noqa: F401 -- committed fixture

from app.core.config import Settings
from app.models import LoginSession, PasswordReset, User, utcnow
from app.security import COOKIE_NAME, hasher, token_hash, verify_password
from app.services import password_reset

pytestmark = pytest.mark.database
NEW_PASSWORD = "a-new-long-reset-passphrase"


@pytest.fixture
def mailbox(client):
    config = client.app.state.settings
    config.smtp_host = "smtp.test"
    config.smtp_username = "test-sender"
    config.smtp_sender = "sender@example.com"
    config.smtp_password = SecretStr("synthetic-smtp-password")
    messages = []
    with patch(
        "app.services.password_reset.send_email",
        side_effect=lambda c, to, subject, body: messages.append((to, subject, body)),
    ):
        yield messages


def issue(client, mailbox, email="person@example.com"):
    response = client.post("/auth/forgot-password", json={"email": email})
    assert response.status_code == 200, response.text
    body = mailbox[-1][2]
    match = re.search(r"#token=([A-Za-z0-9_-]{43})", body)
    assert match is not None
    return match.group(1)


def redeem(client, raw, password=NEW_PASSWORD):
    return client.post("/auth/reset-password", json={"token": raw, "password": password})


def test_reset_hashes_tokens_revokes_all_sessions_and_other_links(client, db, mailbox):
    register(client)
    owner = db.scalar(select(User))
    client.post("/auth/login", json={"email": owner.email, "password": PASSWORD})
    # A second session is retained from another device.
    db.add(
        LoginSession(
            token_hash=token_hash("other-device-token"),
            user_id=owner.id,
            csrf_token="other-csrf",
            expires_at=utcnow() + timedelta(days=1),
        )
    )
    db.commit()
    raw = issue(client, mailbox, "PERSON@example.com")
    other = issue(client, mailbox)
    row = db.get(PasswordReset, token_hash(raw))
    assert row is not None and db.get(PasswordReset, raw) is None
    assert row.expires_at - row.created_at == timedelta(minutes=30)
    assert verify_password(PASSWORD, owner.password_hash)
    response = redeem(client, raw)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    db.expire_all()
    assert verify_password(NEW_PASSWORD, owner.password_hash) and owner.role == "participant"
    assert (
        db.scalar(
            select(func.count()).select_from(LoginSession).where(LoginSession.user_id == owner.id)
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count()).select_from(PasswordReset).where(PasswordReset.user_id == owner.id)
        )
        == 0
    )
    assert client.get("/me").status_code == 401
    assert redeem(client, raw).status_code == redeem(client, other).status_code == 400
    assert (
        client.post("/auth/login", json={"email": owner.email, "password": PASSWORD}).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"email": owner.email, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )
    assert mailbox[-1][1] == "Your rapo password was reset"
    assert NEW_PASSWORD not in mailbox[-1][2] and raw not in mailbox[-1][2]


def test_forgot_has_generic_response_and_address_rate_limit(client, db, mailbox):
    register(client)
    known = client.post("/auth/forgot-password", json={"email": "person@example.com"})
    missing = client.post("/auth/forgot-password", json={"email": "missing@example.com"})
    assert known.status_code == missing.status_code == 200 and known.json() == missing.json()
    assert len(mailbox) == 1
    for _ in range(5):
        assert (
            client.post("/auth/forgot-password", json={"email": "PERSON@example.com"}).json()
            == known.json()
        )
    assert len(mailbox) == 3
    assert db.scalar(select(func.count()).select_from(PasswordReset)) == 3
    assert "token" not in known.text and known.headers["cache-control"] == "no-store"


def test_unconfigured_mail_is_uniform_and_does_not_create_tokens(client, db):
    client.app.state.settings.smtp_password = None
    register(client)
    known = client.post("/auth/forgot-password", json={"email": "person@example.com"})
    missing = client.post("/auth/forgot-password", json={"email": "missing@example.com"})
    assert known.status_code == missing.status_code == 503 and known.json() == missing.json()
    assert db.scalar(select(func.count()).select_from(PasswordReset)) == 0


@pytest.mark.parametrize("offset", [-1, 0])
def test_expired_boundary_and_invalid_token_share_error(client, db, mailbox, offset):
    register(client)
    raw = issue(client, mailbox)
    row = db.get(PasswordReset, token_hash(raw))
    instant = row.expires_at + timedelta(seconds=offset)
    # At expiry the link is already invalid; a second later is also invalid.
    with patch("app.services.password_reset.utcnow", return_value=instant + timedelta(seconds=1)):
        expired = redeem(client, raw)
    invalid = redeem(client, secrets.token_urlsafe(32))
    assert expired.status_code == invalid.status_code == 400 and expired.json() == invalid.json()


def test_reset_validation_origin_and_ip_limit(client, db, mailbox):
    register(client)
    raw = issue(client, mailbox)
    weak = redeem(client, raw, "tiny-value")
    assert weak.status_code == 422 and "tiny-value" not in weak.text and raw not in weak.text
    assert (
        client.post(
            "/auth/reset-password",
            json={"token": raw, "password": NEW_PASSWORD},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    client.app.state.settings.auth_rate_limit = 1
    # Existing failed attempts have persisted, so both endpoints now hit the IP limit.
    assert redeem(client, raw).status_code == 429
    assert (
        client.post("/auth/forgot-password", json={"email": "person@example.com"}).status_code
        == 429
    )
    assert db.get(PasswordReset, token_hash(raw)) is not None


def test_delivery_failure_is_private_and_does_not_reset_password(client, db, mailbox, caplog):
    register(client)
    with patch(
        "app.services.password_reset.send_email", side_effect=RuntimeError("smtp-password-secret")
    ):
        assert (
            client.post("/auth/forgot-password", json={"email": "person@example.com"}).status_code
            == 200
        )
    assert verify_password(PASSWORD, db.scalar(select(User)).password_hash)
    assert "smtp-password-secret" not in caplog.text and "person@example.com" not in caplog.text


def test_reset_rolls_back_password_sessions_and_tokens(client, db, connection, mailbox):
    register(client)
    raw = issue(client, mailbox)

    def fail_after_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("DELETE FROM password_resets"):
            raise RuntimeError("Simulated transaction failure")

    sql_event.listen(connection, "after_cursor_execute", fail_after_delete)
    try:
        with pytest.raises(RuntimeError):
            redeem(client, raw)
    finally:
        sql_event.remove(connection, "after_cursor_execute", fail_after_delete)
    db.expire_all()
    assert verify_password(PASSWORD, db.scalar(select(User)).password_hash)
    assert db.get(PasswordReset, token_hash(raw)) is not None
    assert client.get("/me").status_code == 200


def test_confirmation_delivery_failure_does_not_undo_reset(client, db, mailbox, caplog):
    register(client)
    raw = issue(client, mailbox)
    with patch(
        "app.services.password_reset.send_email", side_effect=RuntimeError("private-detail")
    ):
        assert redeem(client, raw).status_code == 200
    db.expire_all()
    assert verify_password(NEW_PASSWORD, db.scalar(select(User)).password_hash)
    assert db.get(PasswordReset, token_hash(raw)) is None
    assert "private-detail" not in caplog.text


def test_failed_token_commit_sends_no_email(client, db, connection, mailbox):
    register(client)

    def fail_token_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("INSERT INTO password_resets"):
            raise RuntimeError("Simulated token persistence failure")

    sql_event.listen(connection, "after_cursor_execute", fail_token_insert)
    try:
        response = client.post("/auth/forgot-password", json={"email": "person@example.com"})
        assert response.status_code == 200
    finally:
        sql_event.remove(connection, "after_cursor_execute", fail_token_insert)
    assert mailbox == []
    assert db.scalar(select(func.count()).select_from(PasswordReset)) == 0
    assert client.get("/me").status_code == 200


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/?secret=x",
        "https://example.com/path",
        "https://example.com/#fragment",
    ],
)
def test_trusted_reset_origin_validation(url):
    with pytest.raises(ValidationError):
        Settings(reset_frontend_url=url)


def test_smtp_uses_tls_and_authenticated_delivery():
    config = Settings(
        smtp_host="smtp.test",
        smtp_security="starttls",
        smtp_username="sender",
        smtp_password="synthetic-password",
        smtp_sender="sender@example.com",
    )
    with patch("app.services.password_reset.smtplib.SMTP") as smtp:
        password_reset.send_email(config, "recipient@example.com", "Reset", "Body")
        transport = smtp.return_value.__enter__.return_value
        transport.starttls.assert_called_once()
        transport.login.assert_called_once_with("sender", "synthetic-password")
        message = transport.send_message.call_args.args[0]
        assert message["To"] == "recipient@example.com"
    with patch("app.services.password_reset.smtplib.SMTP_SSL") as smtp:
        config.smtp_security = "ssl"
        password_reset.send_email(config, "recipient@example.com", "Reset", "Body")
        smtp.return_value.__enter__.return_value.login.assert_called_once()


def test_competing_resets_use_link_once(race_setup, database_engine):  # noqa: F811
    app, event_id, tokens = race_setup
    raw = secrets.token_urlsafe(32)
    with Session(database_engine) as db:
        owner_id = db.scalar(
            select(User.id)
            .join(LoginSession)
            .where(LoginSession.token_hash == token_hash(tokens[0]))
        )
        db.add(
            PasswordReset(
                token_hash=token_hash(raw),
                user_id=owner_id,
                created_at=utcnow(),
                expires_at=utcnow() + timedelta(minutes=30),
            )
        )
        db.commit()
    barrier = Barrier(2)

    def reset():
        with TestClient(app, base_url="http://127.0.0.1:8000") as worker:
            barrier.wait(timeout=10)
            return worker.post(
                "/auth/reset-password", json={"token": raw, "password": NEW_PASSWORD}
            ).status_code

    with (
        patch("app.services.password_reset.notify_reset"),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        assert sorted(pool.map(lambda _: reset(), range(2))) == [200, 400]
    with Session(database_engine) as db:
        assert db.get(PasswordReset, token_hash(raw)) is None
        assert not db.scalar(
            select(LoginSession.token_hash).where(LoginSession.user_id == owner_id)
        )


def test_old_password_login_cannot_survive_concurrent_reset(race_setup, database_engine):  # noqa: F811
    app, event_id, tokens = race_setup
    raw = secrets.token_urlsafe(32)
    new_hash = hasher.hash(NEW_PASSWORD)
    old_hash = hasher.hash(PASSWORD)
    with Session(database_engine) as db:
        user = db.scalar(
            select(User).join(LoginSession).where(LoginSession.token_hash == token_hash(tokens[0]))
        )
        user.password_hash = old_hash
        email = user.email
        db.add(
            PasswordReset(
                token_hash=token_hash(raw),
                user_id=user.id,
                created_at=utcnow(),
                expires_at=utcnow() + timedelta(minutes=30),
            )
        )
        db.commit()
    login_locked, release_login = ThreadEvent(), ThreadEvent()

    def verify(password, encoded):
        login_locked.set()
        assert release_login.wait(timeout=10)
        return verify_password(password, encoded)

    def login():
        with TestClient(app, base_url="http://127.0.0.1:8000") as worker:
            response = worker.post("/auth/login", json={"email": email, "password": PASSWORD})
            assert response.status_code == 200
            return worker.cookies[COOKIE_NAME]

    def reset():
        with TestClient(app, base_url="http://127.0.0.1:8000") as worker:
            return worker.post(
                "/auth/reset-password", json={"token": raw, "password": NEW_PASSWORD}
            ).status_code

    with (
        patch("app.routers.auth.verify_password", side_effect=verify),
        patch("app.services.password_reset.hasher", SimpleNamespace(hash=lambda _: new_hash)),
        patch("app.services.password_reset.notify_reset"),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        logging_in = pool.submit(login)
        assert login_locked.wait(timeout=10)
        resetting = pool.submit(reset)
        try:
            with pytest.raises(FutureTimeout):
                resetting.result(timeout=1)
        finally:
            release_login.set()
        session = logging_in.result(timeout=10)
        assert resetting.result(timeout=10) == 200
    with TestClient(app, base_url="http://127.0.0.1:8000") as worker:
        worker.cookies.set(COOKIE_NAME, session)
        assert worker.get("/me").status_code == 401
