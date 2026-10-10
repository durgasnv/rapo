import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuthRateLimit, LoginSession, User, utcnow

Db = Annotated[Session, Depends(get_db, scope="function")]
COOKIE_NAME = "rapo_session"
hasher = PasswordHasher()
# Unknown accounts still do password verification to reduce timing-based enumeration.
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in request.app.state.settings.cors_origins:
        raise HTTPException(403, "This origin is not allowed")


def guard_auth(request: Request, db: Db) -> None:
    check_origin(request)
    config = request.app.state.settings
    now = utcnow()
    key = token_hash(f"auth:{request.client.host if request.client else 'unknown'}")
    reset = now + timedelta(seconds=config.auth_rate_window_seconds)
    db.execute(delete(AuthRateLimit).where(AuthRateLimit.reset_at <= now))
    statement = insert(AuthRateLimit).values(key=key, attempts=1, reset_at=reset)
    increment = statement.on_conflict_do_update(
        index_elements=[AuthRateLimit.key],
        set_={
            "attempts": case((AuthRateLimit.reset_at <= now, 1), else_=AuthRateLimit.attempts + 1),
            "reset_at": case((AuthRateLimit.reset_at <= now, reset), else_=AuthRateLimit.reset_at),
        },
    ).returning(AuthRateLimit.attempts)
    attempts = db.execute(increment).scalar_one()
    # Failed authentication also consumes an attempt, so persist before raising an HTTP error.
    db.commit()
    if attempts > config.auth_rate_limit:
        raise HTTPException(
            429,
            "Too many attempts. Please try again later.",
            headers={"Retry-After": str(config.auth_rate_window_seconds)},
        )


@dataclass
class Identity:
    user: User
    session: LoginSession


def get_identity(request: Request, db: Db) -> Identity:
    raw = request.cookies.get(COOKIE_NAME, "")
    session = db.get(LoginSession, token_hash(raw)) if raw else None
    if session is None or session.expires_at <= utcnow():
        raise HTTPException(401, "Please sign in")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "Please sign in")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(supplied.encode(), session.csrf_token.encode()):
            raise HTTPException(403, "Invalid CSRF token. Refresh the page and try again.")
    return Identity(user, session)


CurrentIdentity = Annotated[Identity, Depends(get_identity)]


def get_organizer(identity: CurrentIdentity) -> User:
    if identity.user.role != "organizer":
        raise HTTPException(403, "Organizer access is required")
    return identity.user


Organizer = Annotated[User, Depends(get_organizer)]


def start_session(user: User, db: Session, request: Request, response: Response) -> LoginSession:
    config = request.app.state.settings
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(old_token)))
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= utcnow()))
    raw_token = secrets.token_urlsafe(32)
    session = LoginSession(
        token_hash=token_hash(raw_token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(seconds=config.session_ttl_seconds),
    )
    db.add(session)
    db.flush()
    response.set_cookie(
        COOKIE_NAME,
        raw_token,
        max_age=config.session_ttl_seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return session
