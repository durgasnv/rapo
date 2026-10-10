# Database and migrations

## Purpose

PostgreSQL now stores accounts, sessions, authentication rate counters, events,
event registrations, and audit records. SQLAlchemy models describe the application
view of these tables. Alembic migrations describe how to create or change the real schema.

## Setup and data flow

Copy `apps/api/.env.example` to `apps/api/.env`, match its connection URL to the
root Compose configuration, then run:

```bash
uv run --env-file apps/api/.env alembic upgrade head
```

The initial migration creates UUID identifiers, foreign keys, unique email
addresses, indexes, allowed roles/statuses, and event date/team-size constraints.
No tables are created implicitly when the API starts. `/health` stays independent
of PostgreSQL so liveness does not hide a database configuration problem.

An API request gets a SQLAlchemy session. Its transaction commits before the
response is sent, using FastAPI's function-scoped dependency cleanup. Exceptions
roll it back. Authentication rate counters deliberately commit separately so a
failed login still consumes an attempt. Event edits acquire a row lock and check
the submitted version to avoid overwriting another browser's changes.

## Schema changes

After changing models, generate and review a migration:

```bash
uv run --env-file apps/api/.env alembic revision --autogenerate -m 'describe the schema change'
uv run --env-file apps/api/.env alembic upgrade head
uv run --env-file apps/api/.env alembic check
```

Review generated SQL and data effects before applying a migration. The initial
revision has a downgrade for empty development databases; downgrading to `base`
drops all application tables. Production changes need backups and an explicit
recovery plan. Never use a destructive downgrade to fix a development password.

## Tests and isolation

Integration tests require `RAPO_TEST_DATABASE_URL` with a database name ending in
`_test`. Each suite allocates a random PostgreSQL schema, applies real migrations
there, and compares them with model metadata. Each test runs in a transaction
with savepoints so request-level commits can be rolled back after the test.
Cleanup drops only the schema created by that suite. Existing schemas and their
data are preserved, including accounts created by browser tests.

This verifies PostgreSQL behavior directly rather than substituting SQLite's
different locking, type, and constraint behavior. Unit/health tests can run
without a database; missing database configuration skips integration tests.
CI supplies the URL explicitly and runs the complete suite.

## Boundaries

The schema now contains the Phase 1 and Phase 2 domains. The Phase 2 migration
adds registrations, unique user/event rows, unique event-local queue tickets,
status checks, and lookup indexes. See [registration](../features/event-registration.md)
and [transactions](transaction-and-concurrency.md) for the locking protocol.
Teams, grouping runs, and history tables will arrive with the phases that use them. The event status check
currently permits `DRAFT`, `PUBLISHED`, and `CANCELLED`; later lifecycle states
will require a migration.

See [SQLAlchemy transaction documentation](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
and [Alembic migration documentation](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
for the underlying tools.
