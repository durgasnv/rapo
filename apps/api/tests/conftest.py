import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.db import get_db, make_engine
from app.main import create_app


@pytest.fixture(scope="session")
def database_engine() -> Iterator[Engine]:
    url = os.environ.get("RAPO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set RAPO_TEST_DATABASE_URL to run PostgreSQL integration tests")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Integration tests require a dedicated database ending in _test")
    root = Path(__file__).resolve().parents[3]
    schema = f"test_{uuid4().hex}"
    admin_engine = make_engine(url)
    with admin_engine.begin() as admin:
        admin.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with patch.dict(os.environ, {"RAPO_DATABASE_URL": url}), engine.begin() as connection:
            configuration = Config(str(root / "alembic.ini"))
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, "head")
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as admin:
            admin.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def connection(database_engine: Engine) -> Iterator[Connection]:
    with database_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        yield session


@pytest.fixture
def client(connection: Connection) -> Iterator[TestClient]:
    application = create_app(Settings(auth_rate_limit=100))

    def override_db() -> Iterator[Session]:
        with Session(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    application.dependency_overrides[get_db] = override_db
    with TestClient(application, base_url="http://127.0.0.1:8000") as test_client:
        test_client.headers["Origin"] = "http://127.0.0.1:3000"
        yield test_client
