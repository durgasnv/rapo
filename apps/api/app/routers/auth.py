from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import User
from app.security import (
    COOKIE_NAME,
    DUMMY_HASH,
    CurrentIdentity,
    Db,
    guard_auth,
    hasher,
    start_session,
    verify_password,
)

router = APIRouter(tags=["authentication"])


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class RegisterInput(LoginInput):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    password: SecretStr = Field(min_length=12, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: str
    role: str


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


@router.post(
    "/auth/register", response_model=SessionOut, status_code=201, dependencies=[Depends(guard_auth)]
)
def register(body: RegisterInput, request: Request, response: Response, db: Db) -> SessionOut:
    user = User(
        name=body.name,
        email=str(body.email).lower(),
        password_hash=hasher.hash(body.password.get_secret_value()),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as error:
        raise HTTPException(409, "An account with this email already exists") from error
    session = start_session(user, db, request, response)
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


@router.post("/auth/login", response_model=SessionOut, dependencies=[Depends(guard_auth)])
def login(body: LoginInput, request: Request, response: Response, db: Db) -> SessionOut:
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    password = body.password.get_secret_value()
    if not verify_password(password, user.password_hash if user else DUMMY_HASH) or user is None:
        raise HTTPException(401, "Email or password is incorrect")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(password)
    session = start_session(user, db, request, response)
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


@router.get("/me", response_model=SessionOut)
def me(identity: CurrentIdentity, response: Response) -> SessionOut:
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(
        user=UserOut.model_validate(identity.user), csrf_token=identity.session.csrf_token
    )


@router.post("/auth/logout", status_code=204)
def logout(identity: CurrentIdentity, db: Db, response: Response, request: Request) -> None:
    db.delete(identity.session)
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
