"""Explicit operator commands; credentials stay out of arguments and output."""

import argparse
import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.services.password_reset import send_email


def libpq_environment(database_url: str) -> dict[str, str]:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("A PostgreSQL database URL is required")
    env = os.environ.copy()
    env.update(
        PGHOST=url.host or "localhost",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
        PGDATABASE=url.database or "",
    )
    query_keys = {
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "options": "PGOPTIONS",
        "connect_timeout": "PGCONNECT_TIMEOUT",
        "channel_binding": "PGCHANNELBINDING",
        "application_name": "PGAPPNAME",
    }
    for key, value in url.query.items():
        if key not in query_keys or not isinstance(value, str):
            raise ValueError("Unsupported PostgreSQL connection option")
        env[query_keys[key]] = value
    env["PGCONNECT_TIMEOUT"] = "10"
    return env


def backup(database_url: str, destination: Path) -> None:
    env = libpq_environment(database_url)
    # Exclusive creation prevents overwriting a previous backup or following a symlink.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            subprocess.run(
                ["pg_dump", "--format=custom", "--no-owner", "--no-acl"],
                env=env,
                stdout=output,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=600,
            )
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def restore_check(database_url: str, source: Path) -> None:
    url = make_url(database_url)
    if not (url.database or "").endswith("_restore_test"):
        raise ValueError("Restore checks require a disposable database ending in _restore_test")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            occupied = connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema'))"
                )
            )
        if occupied:
            raise ValueError("Restore checks require an empty database")
        subprocess.run(
            [
                "pg_restore",
                "--dbname=" + (url.database or ""),
                "--single-transaction",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                str(source),
            ],
            env=libpq_environment(database_url),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=600,
        )
        with engine.connect() as connection:
            connection.execute(text("SELECT token_hash FROM password_resets LIMIT 0"))
            connection.execute(text("SELECT id FROM events LIMIT 0"))
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="rapo release and recovery operations")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mail-check", help="Send one verification email to the configured sender")
    commands.add_parser(
        "preflight", help="Check production settings and required mail configuration"
    )
    commands.add_parser("backup").add_argument("file", type=Path)
    commands.add_parser("restore-check").add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        config = Settings()
        if args.command in {"preflight", "mail-check"}:
            from app.services.password_reset import mail_configured

            if config.environment != "production" or not mail_configured(config):
                raise ValueError("Production settings and SMTP credentials are required")
            if args.command == "mail-check":
                assert config.smtp_sender
                send_email(
                    config,
                    str(config.smtp_sender),
                    "rapo deployment mail verification",
                    "rapo connected to the configured SMTP service using TLS. "
                    "This verifies transport only. "
                    "Also test a password reset from the hosted site.",
                )
        elif args.command == "backup":
            backup(config.migration_database_url, args.file)
        else:
            restore_check(config.database_url, args.file)
    except Exception:
        # Provider errors and validation inputs can contain credentials. Keep them private.
        parser.exit(
            1, "Operation failed. Check configuration, connectivity, permissions and tools.\n"
        )
    print("Operation completed.")


if __name__ == "__main__":
    main()
