from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from alembic import command
from app.db import Base

pytestmark = pytest.mark.database


def test_migration_matches_models(connection: Connection) -> None:
    context = MigrationContext.configure(connection)
    assert compare_metadata(context, Base.metadata) == []


def test_database_constraints_are_present(connection: Connection) -> None:
    inspector = inspect(connection)
    assert {"users", "sessions", "events", "audit_logs", "auth_rate_limits"} <= set(
        inspector.get_table_names()
    )
    assert inspector.get_unique_constraints("users")[0]["column_names"] == ["email"]
    names = {constraint["name"] for constraint in inspector.get_check_constraints("events")}
    assert {
        "event_dates",
        "registration_dates",
        "team_sizes",
        "event_capacity",
        "grouping_dates",
    } <= names


def test_migration_downgrade_and_upgrade_in_isolated_schema(connection: Connection) -> None:
    configuration = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    configuration.attributes["connection"] = connection
    command.downgrade(configuration, "base")
    assert "users" not in inspect(connection).get_table_names()
    command.upgrade(configuration, "head")
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
