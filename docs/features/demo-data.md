# Testing with many members

Use the trusted server command to create 120 synthetic participant accounts and
five clearly labelled demo events under an existing organizer. Run it against a
local development database with migrations applied. It writes normal database
records, so the existing UI and API can exercise the full workflow. No new
endpoints, migrations, dependencies, or organizer privileges are added.

From the repository root:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.seed_demo \
  --organizer your-email@example.com
```

Enter a password of 12–128 characters when prompted. All synthetic members use
this password, stored with separate Argon2 salts. The command never prints it.
For scripted runs, supply `RAPO_DEMO_PASSWORD` through the environment; avoid
putting a real password into shell history. Organizer credentials are unchanged.
Only an existing account with organizer access can own the demo.

Open **Manage events** using that organizer account. The command prints the two
management paths:

| Event              | Initial contents                                                                  | What to try                                                                                 |
| ------------------ | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Scheduled Grouping | 100 registered members, 20 FIFO waitlisted, sizes 3–5                             | Generate preview, compare history scores, finalize, inspect registration pagination and CSV |
| Roster Repair      | 33 finalized teams, 98 active members, 20 waiting, one declined and one withdrawn | Replace vacancies, inspect pending confirmations and two ready teams, reassign members      |
| History 1–3        | Three completed events, 100 members each                                          | Supply actual completed-team collaboration history to the grouping engine                   |

Registration is already closed on the two current events. Grouping is due, the
confirmation deadline is five days away, and the events start in seven days.
The running grouping worker may create the scheduled preview immediately after
seeding commits. It does not finalize it. Without a worker, generate the preview
manually, or run:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.jobs.grouping --once
```

The first two historical rounds reuse teams of four. The third shifts membership
by two, giving pair frequencies of one, two, and three. Their
`demo-history-v1` runs are explicitly constructed fixtures, not optimization
results. Historical memberships use final teams and confirmed assignments, with
valid past schedules and scores computed against preceding completed rounds.
The current roster is generated and finalized through the existing services;
its decline, withdrawal, and confirmations also use normal lifecycle services.
These actions create the usual audit entries and in-app notifications.

To test the participant view, use a separate browser profile and sign in as
`demo.large-demo.001@example.com` through
`demo.large-demo.120@example.com`, with the password you supplied. Members
101–120 initially wait in both current events. Replacing the first roster vacancy
selects member 101 through the existing FIFO policy. Confirmations reset when a
team changes. New members have zero collaboration history; registration itself
does not assign a team. History-aware grouping occurs after registration closes.
Post-finalization replacements use FIFO, not a new global grouping search.

## Repeats, isolation, and recovery

The default namespace is `large-demo`. Repeating the command preserves every UI
edit, confirmation, withdrawal, password, and existing queue ticket. It does not
reset dates, so an old demo eventually passes its deadlines. Use a new namespace
for a fresh independent demo:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.seed_demo \
  --organizer your-email@example.com --namespace practice-2
```

That creates accounts named `demo.practice-2.001@example.com`, etc. Namespaces
contain 1–32 lowercase letters, digits, or hyphens and start with a letter or
digit. Each new namespace adds 120 accounts and five events; use fresh names
sparingly. There is no destructive reset or cleanup command. Do not seed a
production database: these are synthetic accounts sharing a demo password.

Deterministic UUIDs and synthetic email addresses isolate each namespace. A
PostgreSQL transaction advisory lock serializes commands using the same
namespace. All accounts, historical memberships, current events, notifications,
and the `demo.seeded` audit marker commit together. A failure rolls everything
back. A completed marker makes retries no-ops. A namespace owned by another
organizer, a colliding existing account, or a colliding event causes an error;
existing records are never adopted or overwritten. Choose another namespace
rather than deleting existing data.

## Concurrent registration check

The demo seed prepares fixtures directly, so it is not a registration load test.
A separate integration test sends 120 real ASGI HTTP registration requests with
16 concurrent workers against an isolated PostgreSQL test schema. It verifies
exactly 100 registered, 20 waitlisted, unique queue tickets 1–120, and no duplicate
registrations after retrying all 120 requests. Authentication sessions are
prepared directly so this measures registration, rather than password hashing
or the signup rate limiter.

```bash
RAPO_TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:55433/rapo_demo_test \
  uv run pytest -q -s apps/api/tests/test_registration_load.py
```

Use a disposable database whose name ends in `_test`. The fixture migrates a
unique schema and drops that schema afterward. The test prints total elapsed
time plus median, p95, and maximum request latency. Sixteen workers bound resource
use; the requests run concurrently in a queue, not all 120 at the same instant.
Measurements include the in-process HTTP client, application, and database;
they exclude network, browser rendering, and deployment infrastructure. There
are no hardware-dependent latency assertions and these numbers are not a
production capacity guarantee. Grouping still supports at most 100 eligible
members per event; waitlisted members do not count toward that limit.

`test_demo_data.py` additionally verifies exact participant coverage and team
sizes, repeated collaboration frequencies, confirmations and vacancy repair,
password verification, non-destructive repeats, authorization/collision checks,
and rollback after a mid-seed failure.
