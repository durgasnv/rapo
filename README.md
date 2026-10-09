# rapo.

**Less repetition. More connection.**

rapo. is a web platform for event registration and fair, history-aware team
formation. The current implementation is the Phase 0 foundation: a Next.js page
that calls a FastAPI health endpoint, local PostgreSQL configuration, and CI.
Accounts, events, and team formation are planned and are not implemented yet.

## Prerequisites

- Node.js 22 LTS (22.13 or newer) and npm.
- Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Docker with Docker Compose and a running daemon.

Run all commands below from the repository root. The repository itself is the
monorepo; do not create another `rapo/` directory inside it.

## Local setup

```bash
npm ci
uv sync --locked
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
```

Set a local database password in `.env`, then start PostgreSQL:

```bash
docker compose up -d --wait db
```

Start the API in one terminal:

```bash
uv run uvicorn app.main:app --app-dir apps/api --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another:

```bash
npm run dev
```

Open <http://localhost:3000>. The service status should show “Connected to rapo.”
and `{ "status": "ok" }`. API documentation is at <http://localhost:8000/docs>.
The health endpoint reports API liveness only; it does not query PostgreSQL.

## Configuration

| Variable                                            | Where                   | Purpose                                                                                  |
| --------------------------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`                               | `apps/web/.env.local`   | Browser-visible API base URL; defaults to `http://localhost:8000`                        |
| `RAPO_CORS_ORIGINS`                                 | API process environment | JSON array of allowed frontend origins; defaults to localhost and 127.0.0.1 on port 3000 |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Root `.env`             | Local PostgreSQL configuration                                                           |
| `POSTGRES_PORT`                                     | Root `.env`             | Host port for PostgreSQL; defaults to 5432                                               |

Restart Next.js after changing its environment file. The API reads environment
variables from its process; it does not load the root `.env` automatically.
Database passwords belong only on the server and must never use a
`NEXT_PUBLIC_` variable. PostgreSQL binds to the local loopback interface.

## Checks

```bash
npm run format:check
npm run lint
npm run typecheck
npm run build
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
npx playwright install --with-deps chromium
npm run test:e2e
```

The browser tests start their own API and frontend on ports 8000 and 3000. Stop
existing development servers first. They verify a live API request and recovery
from a failed request. CI also starts PostgreSQL and executes `SELECT 1`.

Use `npm run format` for web/config/document formatting and `uv run ruff format .`
for Python. Stop PostgreSQL with `docker compose down`; its named volume preserves
local data. Changing `.env` credentials does not change an initialized database's
credentials. Do not remove the volume unless you intend to delete its data.

## Structure and next steps

- `apps/web`: Next.js, React, TypeScript, Tailwind CSS.
- `apps/api`: FastAPI application and API tests.
- `tests/e2e`: Playwright browser checks.
- `.github/workflows/ci.yml`: formatting, lint, types, tests, build, database check.
- [Development foundation](docs/features/development-foundation.md): request flow,
  design decisions, troubleshooting, and limitations.
- [Requirements](docs/1000_requirement.md), [technical plan](docs/1100_plan.md), and
  [development phases](docs/1200_phases.md): the product roadmap.

Phase 1 will introduce schema migrations, authentication, organizer ownership,
and event management. No deployment is configured yet.
