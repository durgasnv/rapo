# College dataset import

The college fixture can be loaded into the local development database as normal
users, events, registrations, finalized teams, and completed collaboration history.
The existing dashboard and organizer pages read these records through the existing
API. No frontend mocks, schema changes, or additional services are required.

## Load and explore

Start the local database and apply migrations first. From the repository root:

```bash
docker compose up -d --wait db
uv run --env-file apps/api/.env alembic upgrade head
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.import_college \
  --organizer durgashree.nv29@gmail.com
```

The owner must already exist with organizer access. The command never creates or
promotes an organizer, changes their password, or sends email. It requires a
development environment and a PostgreSQL URL with a loopback hostname, and refuses
remote databases. Keep the local database port in `apps/api/.env` consistent with
Docker's published port. A refused connection means the database must be started
before importing; enabling Docker Desktop WSL integration may be necessary.

Supply a separate demo password of 12–128 characters at the hidden prompt. For
automation, supply `RAPO_DEMO_PASSWORD` through a local environment file; never
commit it or put a real account password into command history. Each participant
gets an independently salted Argon2 hash. Original college email addresses are
replaced with isolated `demo.college.004@example.com` through
`demo.college.080@example.com` logins. Names are retained; department and year have
no app profile fields and are not stored. The three source organizer profiles are
not imported; all seven events belong to the specified existing organizer.

Sign in as the organizer and open **Manage events** to see seven events labelled
`[DEMO college]`. The command also prints their management paths. In another
browser profile, sign in as a synthetic participant with the supplied demo
password. Public event discovery includes the two published events and the
finalized event; drafts remain private and completed events supply history.
The participant's registrations and own team use the existing dashboard and team
API permissions.

## Preserved states and dates

The fixture contains 77 participants, 185 registrations, two completed events, one
finalized event, two published events, and two drafts. Completed team memberships
become finalized teams with confirmed assignments, so future grouping uses actual
historical collaborations. The finalized preview retains all 28 original members;
its current roster has 26 active assignments. The declined and withdrawn members'
registrations are normalized to cancelled, matching the application's lifecycle.
Waitlist tickets and other assignment states are preserved.

Imported runs are labelled `dataset-import-v1`. Their scores and history snapshots
are computed from preceding completed teams, instead of trusting illustrative JSON
metrics. Evaluation counts are zero and baseline scores equal the imported
arrangement: this command imports membership, rather than running optimization.
No lifecycle notifications are manufactured. Import audit entries identify demo
setup.

Dates are preserved by default. The IEEE event ends in October 2026, so its roster
becomes read-only after its start. Other registration and grouping actions also
respect the original windows. For a separate fixture with explicitly shifted
dates, use a fresh namespace:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.import_college \
  --organizer durgashree.nv29@gmail.com --namespace college-practice --shift-days 14
```

Choose the shift for the date you are testing. All schedule fields move together;
the command refuses to move completed history into the future. It does not reopen
events, auto-finalize groupings, or change application scheduling policy.

## Validation, retries, and recovery

Validate the source without a database or password using:

```bash
PYTHONPATH=apps/api uv run python -m app.import_college \
  --organizer durgashree.nv29@gmail.com --check
```

The Pydantic graph validator checks schedules, references, source registration
counts, capacities, unique queue tickets, team sizes, exact member coverage, and
matching assignments before any writes. Source roles cannot grant privileges.

One transaction writes the entire fixture. A PostgreSQL advisory lock serializes
imports using the same namespace; deterministic IDs and synthetic email addresses
prevent accidental account adoption. A failure rolls back all imported records.
An audit marker records a fingerprint of the supported source fields and the date
shift. Repeating an identical import preserves UI edits, passwords, and queue
tickets. Different source data, another owner, or a different date shift requires
a new namespace. Existing account/event collisions fail without overwriting data.
There is no destructive reset command; each new namespace adds another fixture.

## Verification and review

`apps/api/tests/test_dataset_import.py` exercises malformed relationships, database
counts, exact completed-event pair frequencies without double counting, real
history-aware preview generation, participant login, organizer event visibility,
own-team privacy, draft protection, safe retries/collisions, CLI database guards,
and transaction rollback after an injected mid-import failure. Integration tests
require `RAPO_TEST_DATABASE_URL` pointing to a dedicated database ending in `_test`.

The integration follows the existing modular API/database architecture and fair
grouping rules. It adds no production route, permissions, dependencies, or migrations.
The original source emails and unsupported profile fields stay outside the database.
This fixture is development data sharing a demo password; use the local-only CLI.
Actual loading still requires a running local database and the existing organizer.

Verified on 2026-10-20 against disposable PostgreSQL 16 on port 55435:

- Full backend suite: `215 passed` (one existing TestClient deprecation warning).
- Importer suite: `15 passed`, including signup → registration → grouping.
- Ruff lint/format and mypy passed; the selected JSON and documentation passed Prettier.
- The real CLI imported 77 participants and seven events; its retry preserved the import.
- `--check` reported `Validated 7 events and 80 source profiles.`

The configured application database on port 55432 was unavailable, and Docker
Desktop reported missing WSL integration. The requested local application import
was therefore not performed. No browser session or deployed-site test was run for
this backend-only change; API integration tests cover the existing UI contracts.
