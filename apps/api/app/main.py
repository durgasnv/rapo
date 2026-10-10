from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from app.core.config import Settings
from app.db import make_engine
from app.routers import auth, events, grouping, registrations


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    engine = make_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    application = FastAPI(title="rapo. API", version="0.1.0", lifespan=lifespan)
    application.state.settings = config
    application.state.engine = engine

    @application.middleware("http")
    async def private_no_store(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if (
            request.url.path == "/me"
            or request.url.path.startswith(("/auth/", "/organizer/", "/me/"))
            or "/grouping-runs" in request.url.path
            or request.url.path.endswith(("/registration", "/registrations", "/register"))
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Validation responses must never echo passwords or other raw request values.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                    for item in error.errors()
                ]
            },
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse()

    application.include_router(auth.router)
    application.include_router(events.router)
    application.include_router(registrations.router)
    application.include_router(grouping.router)
    return application


app = create_app()
