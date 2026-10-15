# Development foundation

This document records the original Phase 0 slice. Phase 1 adds
[accounts](authentication.md), [events](event-management.md), and a
[database schema](../concepts/database-and-migrations.md). See the README for
current setup commands and verification.

The deployment slice now defaults browser requests to the same-origin `/api`
proxy. The direct browser-to-port-8000 flow below records the original Phase 0
behavior and remains available through an explicit local API URL override.

## Purpose and user experience

Phase 0 proves that the browser and API can communicate before we add accounts or
event rules. The landing page introduces rapo. and displays a service status.
While the request is pending it announces “Checking connection…”. A successful
request displays the health JSON. Failure shows a retry button; no participant
data is collected.

## Request flow

```text
Browser loads Next.js page on port 3000
    → React service-status component calls API /health on port 8000
    → FastAPI validates the browser origin through CORS middleware
    → API returns { "status": "ok" }
    → Browser displays connection status
```

The browser makes the request directly, so this verifies browser-to-API
connectivity and CORS rather than just connectivity between servers. The frontend
and API use different ports because they are separate development servers.
[Next.js installation documentation](https://nextjs.org/docs/app/getting-started/installation)
describes the frontend development server;
[FastAPI CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/)
explains why a different port is a different origin.

CORS controls whether browser scripts may read cross-origin responses. It does
not authenticate users or prevent non-browser clients from calling the API.
The API currently allows only GET requests from the configured local frontend
origins. Authentication will require its own authorization and cookie/CSRF policy.

## Components and design decisions

- `apps/web/app/service-status.tsx` owns loading, success, failure, and retry state.
  It checks both HTTP status and the response shape, aborts requests after five
  seconds, and cancels work when unmounted. Status messages use a live region.
- `apps/api/app/main.py` exposes a typed health response and an application factory
  so tests can supply their own configuration.
- `apps/api/app/core/config.py` reads the `RAPO_CORS_ORIGINS` environment setting.
- `docker-compose.yml` runs PostgreSQL with a health check and a persistent named
  volume. The API does not yet connect to it; database models and Alembic belong
  to Phase 1. Keeping liveness independent of the database makes failures easier
  to distinguish. A separate readiness check can be added with database access.
- Root npm workspaces manage the frontend; root `pyproject.toml` manages Python
  tooling through uv. Both dependency trees have lockfiles for repeatable installs.
- CI runs separate lint and build steps because Next.js builds do not run ESLint.

Phase 0 introduced no scheduler, worker, authentication, or grouping logic.
We use the existing repository root for `apps/`, matching the technical layout
without nesting another repository directory.

## Configuration and privacy

The browser needs only the public API URL. Database credentials stay in a local,
ignored root `.env` file. Never expose secrets through Next.js public environment
variables. The Compose database is reachable only through the host's loopback
address. The frontend and API dev servers also bind to loopback by default.

## Verification and failure cases

API tests check the exact health contract, a configured allowed origin, and an
unknown origin. Playwright checks a real successful browser request, then simulates
a network failure and verifies that retry recovers against the live API. CI
checks formatting, lint, TypeScript, Python types, API tests, the frontend build,
Compose syntax, PostgreSQL startup/query, and the browser tests.

Bootstrap verification passed: three API tests, two live-browser tests, lint,
formatting, both type checkers, a production frontend build, and a PostgreSQL
health check/query on host port 55432. A fresh copy of the staged project under
`/tmp` also passed frontend checks and the production build. Reads through this
checkout's Windows-mounted filesystem were substantially slower. The coding
sandbox stalled API TestClient communication and prevented Next.js from reading
TypeScript subprocess output; those checks passed outside the sandbox. The first
hosted CI run remains pending.

If the page cannot connect, check that the API is running, the public URL points
to the machine running the API, and the page origin is allowed. `localhost` in a
browser means that browser's machine. A response from `/health` alone does not
prove that CORS or PostgreSQL works. If port 5432 is busy, set `POSTGRES_PORT` to
another local port. If Docker reports a permission error, enable daemon access
for your development account; the application does not change host permissions.

Stopping Compose preserves the volume. Database initialization variables apply
only to an empty volume. Do not delete existing data to resolve a password mismatch.

## Questions to explore

1. Why can an API respond to curl while a browser cannot read its response?
2. Why is a database password private while the API base URL is public?
3. Why should liveness and database readiness answer different questions?
