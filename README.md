# rapo.

**Less repetition. More connection.**

rapo. is a web platform for event registration and fair, history-aware team
formation. The current implementation includes accounts, secure sessions,
organizer-owned event drafts, publication/cancellation, public discovery,
participant registration, FIFO waitlists, history-aware grouping previews,
finalized assignments, confirmations, withdrawals, and organizer roster repair.

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
cp apps/api/.env.example apps/api/.env
```

Set a local database password in `.env`, then start PostgreSQL:

```bash
docker compose up -d --wait db
```

Update `RAPO_DATABASE_URL` in `apps/api/.env` to match the database credentials
and host port in the root `.env`. URL-encode special characters in its password.
Apply the schema, then start the API in one terminal:

```bash
uv run --env-file apps/api/.env alembic upgrade head
uv run --env-file apps/api/.env uvicorn app.main:app --app-dir apps/api --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Start the frontend in another:

```bash
npm run dev
```

Open <http://localhost:3000>, create an account, and explore events. The expandable
service status shows “Connected to rapo.” and `{ "status": "ok" }`.
API documentation is at <http://localhost:8000/docs>.
The health endpoint reports API liveness only; it does not query PostgreSQL.

To try the organizer flow, first create an account, then grant access from the
trusted server terminal:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.cli your-email@example.com
```

Refresh the browser and choose **Manage events**. Drafts stay private until
published. The event form uses UTC schedule inputs and a separate display
timezone. Organizer access cannot be selected during signup.

To try registration, publish an event whose registration window is currently
open. Use separate browser profiles for two participant accounts. With capacity
1 and minimum team size 1, the first gets a seat and the second joins the waitlist.
Withdraw the first before grouping, then refresh the second's registration to see
the promotion. **My account** shows participant statuses; the organizer's event
management page shows the private roster. Rejoining after withdrawal puts a user
at the back of the queue.

To try grouping, open an owned event after registration closes and select
**Generate team preview**. The preview covers active registered participants,
chooses balanced team sizes, and reduces repeated partnerships from completed
team history. It supports up to 100 participants and saves its seed and scores.
Select **Finalize these teams** to approve a fresh proposal before the confirmation
deadline. Participants can then open their team from **My account** and confirm
or decline. The final roster provides vacancy repair, deadline extensions,
validated reassignment, and CSV export.
See [grouping previews](docs/features/grouping-preview.md) for the full flow and limits.

## Try a 120-member demo

Create synthetic members and events under your existing organizer account:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.seed_demo \
  --organizer your-email@example.com
```

Enter a demo password, then open **Manage events**. The demo includes 100 registered
members, 20 waitlisted members, three completed events with repeated teammates,
and a separate finalized roster with confirmations and vacancies. Re-running
preserves your changes; add `--namespace practice-2` for a fresh demo.
See [demo data and concurrent registration testing](docs/features/demo-data.md)
for participant sign-ins, worker behavior, and the 120-request concurrency check.

## Configuration

| Variable                                            | Where                   | Purpose                                                                                  |
| --------------------------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`                               | `apps/web/.env.local`   | Browser-visible API base URL; defaults to `http://localhost:8000`                        |
| `RAPO_CORS_ORIGINS`                                 | API process environment | JSON array of allowed frontend origins; defaults to localhost and 127.0.0.1 on port 3000 |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Root `.env`             | Local PostgreSQL configuration                                                           |
| `POSTGRES_PORT`                                     | Root `.env`             | Host port for PostgreSQL; defaults to 5432                                               |
| `RAPO_DATABASE_URL`                                 | `apps/api/.env`         | SQLAlchemy PostgreSQL connection URL, used by API, migrations, and admin command         |
| `RAPO_COOKIE_SECURE`                                | `apps/api/.env`         | `false` for local HTTP; set `true` for production HTTPS                                  |
| `RAPO_SESSION_TTL_SECONDS`                          | API process environment | Session lifetime; defaults to 86400 seconds                                              |
| `RAPO_AUTH_RATE_LIMIT`                              | API process environment | Shared authentication attempts per client IP/window; defaults to 20                      |
| `RAPO_AUTH_RATE_WINDOW_SECONDS`                     | API process environment | Authentication window; defaults to 60 seconds                                            |

Restart Next.js after changing its environment file. The API reads environment
variables from its process; it does not load the root `.env` automatically.
Database passwords belong only on the server and must never use a
`NEXT_PUBLIC_` variable. PostgreSQL binds to the local loopback interface.
Use the same hostname for the browser and API URL: pair `localhost` with
`localhost`, or `127.0.0.1` with `127.0.0.1`, so same-site session cookies work.
Production deployments need HTTPS, secure cookies, and reviewed proxy settings.

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
```

Without a test URL, PostgreSQL integration tests are skipped. To run all API and
browser tests, create a dedicated test database and use its URL (adjust credentials
and port to match your local setup):

```bash
docker compose exec -T db psql -U rapo -d rapo -c 'CREATE DATABASE rapo_test;'
RAPO_TEST_DATABASE_URL=postgresql+psycopg://rapo:change-me-local-only@localhost:5432/rapo_test uv run pytest
RAPO_DATABASE_URL=postgresql+psycopg://rapo:change-me-local-only@localhost:5432/rapo_test uv run alembic upgrade head
RAPO_DATABASE_URL=postgresql+psycopg://rapo:change-me-local-only@localhost:5432/rapo_test npm run test:e2e
```

Create the test database once. Integration tests use a fresh temporary schema per
suite and roll back individual tests. Concurrency tests commit their own fixtures
inside that isolated schema and clean up afterwards so separate connections can
see them. Browser tests create unique accounts/events
in the test database; they must never point to a production database.

The browser tests start their own API and frontend on ports 8000 and 3000. Stop
existing development servers first. They verify health/retry, signup/login/logout,
session persistence, organizer draft/edit/publish/cancel flows, registration,
FIFO promotion, unlimited capacity, participant/organizer status screens, grouping
previews, lost-response retries, stale/infeasible proposals, and finalization through
confirmation, dropout, replacement, reassignment, deadline extension, and CSV export. CI starts
PostgreSQL, migrates its test database, and runs these checks.

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
- [Database and migrations](docs/concepts/database-and-migrations.md),
  [authentication](docs/features/authentication.md), and
  [event management](docs/features/event-management.md): Phase 1 behavior.
- [Event registration and waitlists](docs/features/event-registration.md): Phase 2
  behavior, retry semantics, privacy, and current limits.
- [Grouping previews](docs/features/grouping-preview.md) and
  [grouping algorithm](docs/concepts/grouping-algorithm.md): Phase 3 behavior,
  scoring, edge cases, and reproducibility.
- [Event activity](docs/features/event-audit.md): owner-only audit timeline with
  readable actions, actor names, timestamps, and pagination.
- [Password reset](docs/features/password-reset.md): Gmail SMTP setup, expiring
  email links, session revocation, recovery, and delivery limitations.
- [Organizer attention overview](docs/features/organizer-attention.md): review
  proposals, grouping failures, vacancies, and overdue confirmations in one panel.
- [Event completion](docs/features/event-completion.md): close ended events and
  make final assignments available to future collaboration history.
- [Final teams and roster repair](docs/features/team-lifecycle.md): Phase 4
  policies, participant actions, owner controls, and recovery.
- [Transactions and concurrency](docs/concepts/transaction-and-concurrency.md): why
  event locks prevent overselling and keep promotions atomic.
- [Requirements](docs/1000_requirement.md), [technical plan](docs/1100_plan.md), and
  [development phases](docs/1200_phases.md): the product roadmap.

Phases 1–4 and the Phase 5 automation slice are implemented. Scheduled processing
and private in-app notifications run locally; public deployment is still pending.
Email password reset is implemented; configure SMTP credentials and verify real
delivery before release. No deployment is configured yet.

### Scheduled worker and notifications

After applying migrations, run a separate worker:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.jobs.grouping
```

Add `--once` to process one bounded batch. Due published events receive a preview
for organizer approval; retries cannot duplicate scheduled runs. **My account**
contains private notifications with unread filtering and mark-as-read controls.
See [scheduled grouping and notifications](docs/features/scheduled-grouping-and-notifications.md)
for retries, privacy, startup, and recovery. Hosting remains a separate Phase 5 step.
