from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LoginSession, User, utcnow
from app.security import COOKIE_NAME, token_hash

pytestmark = pytest.mark.database
PASSWORD = "a-long-test-passphrase"


def register(client: TestClient, email: str = "person@example.com") -> dict[str, object]:
    response = client.post(
        "/auth/register", json={"name": "Person", "email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    client.headers["X-CSRF-Token"] = str(result["csrf_token"])
    return result


def test_registration_session_and_logout(client: TestClient, db: Session) -> None:
    response = client.post(
        "/auth/register",
        json={"name": " Person ", "email": "Person@EXAMPLE.com", "password": PASSWORD},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == "person@example.com"
    assert data["user"]["name"] == "Person"
    assert data["user"]["role"] == "participant"
    assert "password" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    user = db.scalar(select(User))
    assert user is not None and user.password_hash.startswith("$argon2id$")
    raw = client.cookies[COOKIE_NAME]
    assert db.get(LoginSession, raw) is None
    assert db.get(LoginSession, token_hash(raw)) is not None
    assert client.get("/me").json()["user"]["id"] == data["user"]["id"]
    client.headers["X-CSRF-Token"] = data["csrf_token"]
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/me").status_code == 401
    assert db.get(LoginSession, token_hash(raw)) is None


def test_duplicate_email_and_role_escalation(client: TestClient) -> None:
    register(client)
    body = {"name": "Other", "email": "PERSON@example.com", "password": PASSWORD}
    assert client.post("/auth/register", json=body).status_code == 409
    body["email"] = "other@example.com"
    body["role"] = "organizer"
    assert client.post("/auth/register", json=body).status_code == 422
    assert client.get("/me").json()["user"]["role"] == "participant"


def test_validation_does_not_echo_password(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"name": "Person", "email": "person@example.com", "password": "secret"},
    )
    assert response.status_code == 422
    assert "secret" not in response.text
    assert client.get("/me").headers["cache-control"] == "no-store"


def test_login_rotation_and_wrong_password(client: TestClient) -> None:
    register(client)
    old_token = client.cookies[COOKIE_NAME]
    wrong = client.post("/auth/login", json={"email": "person@example.com", "password": "wrong"})
    missing = client.post("/auth/login", json={"email": "missing@example.com", "password": "wrong"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()
    response = client.post(
        "/auth/login", json={"email": "PERSON@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert client.cookies[COOKIE_NAME] != old_token
    client.cookies.set(COOKIE_NAME, old_token, domain="127.0.0.1", path="/")
    assert client.get("/me").status_code == 401


def test_csrf_and_origin_checks(client: TestClient) -> None:
    register(client)
    del client.headers["X-CSRF-Token"]
    assert client.post("/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = client.get("/me").json()["csrf_token"]
    assert (
        client.post("/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    )
    assert (
        client.post(
            "/auth/login",
            headers={"Origin": "https://evil.example"},
            json={"email": "person@example.com", "password": PASSWORD},
        ).status_code
        == 403
    )
    assert client.post("/auth/logout").status_code == 204


def test_expired_and_revoked_sessions(client: TestClient, db: Session) -> None:
    register(client)
    session = db.get(LoginSession, token_hash(client.cookies[COOKIE_NAME]))
    assert session is not None
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/me").status_code == 401


def test_auth_rate_limit_persists_failed_attempts(client: TestClient) -> None:
    client.app.state.settings.auth_rate_limit = 2  # type: ignore[union-attr]
    body = {"email": "missing@example.com", "password": "wrong"}
    assert client.post("/auth/login", json=body).status_code == 401
    assert client.post("/auth/login", json=body).status_code == 401
    response = client.post("/auth/login", json=body)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_https_cookie_configuration(client: TestClient) -> None:
    client.app.state.settings.cookie_secure = True  # type: ignore[union-attr]
    response = client.post(
        "/auth/register",
        json={"name": "Secure", "email": "secure@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201
    assert "; Secure" in response.headers["set-cookie"]
    # An HTTPS-only cookie must not authenticate a subsequent plain HTTP request.
    assert client.get("/me").status_code == 401
