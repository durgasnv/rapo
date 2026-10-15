from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.main import create_app
from app.operations import backup, libpq_environment, restore_check


def production(**overrides):
    values = {
        "environment": "production",
        "cookie_secure": True,
        "reset_frontend_url": "https://rapo.example.com",
        "cors_origins": ["https://rapo.example.com"],
    }
    return Settings(**(values | overrides))


@pytest.mark.parametrize("prefix", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_provider_database_urls_keep_credentials_and_options(prefix):
    value = prefix + "user:encoded%40password@private-db/rapo?sslmode=require"
    config = Settings(database_url=value)
    assert config.database_url == (
        "postgresql+psycopg://user:encoded%40password@private-db/rapo?sslmode=require"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"cookie_secure": False},
        {"reset_frontend_url": "http://localhost:3000"},
        {"cors_origins": []},
        {"cors_origins": ["https://other.example.com"]},
        {"cors_origins": ["https://rapo.example.com", "*"]},
        {"cors_origins": ["https://rapo.example.com", "http://insecure.example.com"]},
        {"cors_origins": ["https://rapo.example.com", "https://user:pass@other.example.com"]},
    ],
)
def test_production_refuses_insecure_configuration(overrides):
    with pytest.raises(ValidationError):
        production(**overrides)


def test_production_accepts_explicit_https_origins():
    assert production().cookie_secure


def test_configuration_error_does_not_echo_secrets():
    with pytest.raises(ValidationError) as caught:
        production(cookie_secure=False, smtp_password="private-smtp-password")
    assert "private-smtp-password" not in str(caught.value)


def test_ready_checks_migrated_database(database_engine):
    with patch("app.main.make_engine", return_value=database_engine):
        with TestClient(create_app()) as client:
            assert client.get("/ready").json() == {"status": "ok"}


def test_ready_does_not_disclose_connection_errors():
    engine = Mock()
    engine.connect.side_effect = OperationalError("secret-db-url", {}, Exception("secret"))
    with patch("app.main.make_engine", return_value=engine):
        with TestClient(create_app()) as client:
            response = client.get("/ready")
            assert response.status_code == 503
            assert response.json() == {"detail": "Service is not ready"}
            assert response.headers["cache-control"] == "no-store"
            assert client.get("/health").status_code == 200


def test_backup_credentials_stay_in_environment():
    env = libpq_environment(
        "postgresql+psycopg://user:encoded%40pass@db/rapo?sslmode=require&channel_binding=require"
    )
    assert env["PGPASSWORD"] == "encoded@pass"
    assert env["PGHOST"] == "db"
    assert env["PGSSLMODE"] == "require"
    assert env["PGCHANNELBINDING"] == "require"
    assert env["PGDATABASE"] == "rapo"


def test_backup_refuses_overwrite_and_removes_failed_output(tmp_path: Path):
    destination = tmp_path / "backup.dump"
    destination.write_bytes(b"existing backup")
    with pytest.raises(FileExistsError):
        backup("postgresql+psycopg://rapo@localhost/rapo", destination)
    assert destination.read_bytes() == b"existing backup"
    destination.unlink()
    with patch("app.operations.subprocess.run", side_effect=OSError("failure")):
        with pytest.raises(OSError):
            backup("postgresql+psycopg://rapo@localhost/rapo", destination)
    assert not destination.exists()


def test_restore_refuses_non_disposable_database(tmp_path: Path):
    with pytest.raises(ValueError, match="disposable"):
        restore_check("postgresql+psycopg://rapo@localhost/production", tmp_path / "backup.dump")
