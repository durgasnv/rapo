# Repository debugging audit

Date: 2026-10-19. Branch: `debug/repository-audit-2026-10-19`.
Base commit: `bcea31c`.

Seven issues were reproduced: four application defects and three CI/test defects.
Each received a focused fix; the ten investigation areas below distinguish
confirmed findings from risks that were tested without reproducing a defect.

## Scope and method

Reviewed application routes/components, HTTP contracts, business services, grouping
engine, SQLAlchemy models, all six migrations, worker, operator commands, deployment
configuration, CI, documentation and test suites. Installed third-party skill
contents were treated as dependencies. The pre-existing untracked `demo/` directory
was preserved and excluded from changes.

Investigation followed `docs/AGENTS.md` and the product requirements, plan and phase
documents. Reproductions ran before fixes. Existing tests were retained. No
dependencies, database schemas, production data, hosting resources or business policies were
changed. Tests use a disposable PostgreSQL 16 cluster on port 55435, with a dedicated
database ending in `_test`; integration fixtures additionally isolate their schemas.
Node 24.18.0 and Python 3.12 were used.

## Architecture and traced interactions

The application is a modular monolith: Next.js 16.4 renders the browser interface;
FastAPI owns authorization, validation and state transitions; SQLAlchemy persists
transactions in PostgreSQL. The standalone worker shares the backend services.

| Journey                 | Frontend → API                                                                  | Service → database → response                                                                                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Account/session         | `auth-form` / `account-provider` → `/auth/register`, `/auth/login`, `/me`       | Argon2 password verification; hashed session tokens in `sessions`; HttpOnly cookie and CSRF token; database role checked on authenticated requests.                                        |
| Password reset          | `password-reset` → `/auth/forgot-password`, `/auth/reset-password`              | Rate limits and hashed reset tokens; TLS SMTP delivery after token commit; redemption locks the user and atomically replaces password and revokes sessions/tokens.                         |
| Event discovery         | Dashboard / `event-list` → `GET /events`                                        | SQL filtering, deterministic sort and pagination over public event states; `EventPage` renders cards.                                                                                      |
| Organizer edits         | `organizer-editor` / `event-form` → `PATCH /events/{id}`                        | Owner/CSRF checks, event row lock, optimistic version, `EventInput` validation; `events` and `audit_logs` commit together.                                                                 |
| Registration            | `event-registration` → register/withdraw endpoints                              | Event lock serializes seat allocation, unique registration and FIFO queue; promotions and notifications commit together.                                                                   |
| Group proposal          | `grouping-preview` → grouping-run endpoints                                     | Eligible registrations plus completed-event collaboration history → deterministic bounded heuristic → immutable proposal teams/members and input fingerprint.                              |
| Finalization and repair | `grouping-preview` / `team-roster` → finalize/confirm/withdraw/repair endpoints | Locked event, stale-input/version checks, unique final assignments, audit and notifications; participant reads limited to their team.                                                      |
| Completion              | Organizer completion action → `/events/{id}/complete`                           | End-time and final-roster checks; retained final assignments become future history; retries do not double-count or duplicate completion audits.                                            |
| Automation              | GitHub schedule / grouping CLI → `jobs/grouping.py`                             | Due events selected with `FOR UPDATE SKIP LOCKED`; deterministic request ID, savepoint rollback, persisted retry status and notifications.                                                 |
| Deployment              | Vercel service rewrites / local Next rewrite → FastAPI                          | Environment configuration separates runtime/migration URLs; `/health` is liveness, `/ready` checks migrated database; release workflow provides explicit migrations and encrypted backups. |

## Ten highest-risk sources investigated

“Risk” below describes the potential impact being investigated, not a claim that an
unconfirmed vulnerability exists.

| #   | Area and potential bug                                                             | Investigation/result                                                                                                                                                                                                                                                                        |
| --- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Authentication/reset races, role escalation, session persistence (high risk)       | Traced session/CSRF/origin checks, login/reset locking, token hashing/revocation and rate limits. Existing auth/reset/concurrency tests pass; no additional demonstrated defect.                                                                                                            |
| 2   | Event validation and schedule arithmetic (medium risk)                             | Confirmed **B2**: valid lower-bound dates raise an uncaught exception. Existing invalid-input and schedule tests otherwise pass.                                                                                                                                                            |
| 3   | Concurrent registration, last seat, FIFO promotion (high risk)                     | Traced event locks, uniqueness and queue tickets; existing concurrency and registration-load tests pass. No reproduced defect.                                                                                                                                                              |
| 4   | Grouping feasibility, historical eligibility, retries and stale inputs (high risk) | Inspected independent heuristic, work limits, scoring/fingerprint and eligibility queries; engine and grouping tests pass. No additional reproduced defect.                                                                                                                                 |
| 5   | Approved preview selection after lifecycle changes (medium risk)                   | Confirmed **B1**: latest lookup can show an unapproved run after finalization ends.                                                                                                                                                                                                         |
| 6   | Final roster integrity, repair consent and participant privacy (high risk)         | Traced finalize/confirm/withdraw/reassign/repair, event locks, idempotency records and composite foreign keys. Existing roster/security/concurrency tests pass. No reproduced authorization bypass.                                                                                         |
| 7   | Worker idempotency, failures and cutoff races (high risk)                          | Traced locked selection, savepoints, retries and notification rollback; automation/concurrency tests pass. No reproduced double grouping.                                                                                                                                                   |
| 8   | Notification/audit ownership, exports and transaction consistency (high risk)      | Reviewed owner-scoped reads, recipient deduplication, CSV formula neutralization and transactional audit/notification writes; existing tests pass. No additional demonstrated defect.                                                                                                       |
| 9   | Frontend serialization and async recovery (medium risk)                            | Confirmed **B3** (silent schedule rounding) and **B4** (stale load error after successful automatic recovery). Added browser reproductions.                                                                                                                                                 |
| 10  | Deployment, migrations and CI boundary configuration (medium risk)                 | Confirmed **B5** (vendored formatting), **B6** (obsolete interception paths), and **B7** (ambiguous dashboard selector with retained events). Reviewed URL aliases, rewrites, migration metadata and release/worker workflows; hosted provider behavior remains outside local verification. |

## Confirmed findings

### B1 — Approved grouping disappears from default lookup

Severity: **Medium**. Fixed in `apps/api/app/services/grouping.py`.

Root cause: `read()` filtered for a finalized run only while the event status was
exactly `GROUPS_FINALIZED`. For `COMPLETED`, `IN_PROGRESS` and `CANCELLED`, it selected
the most recently created run regardless of approval. Finalizing an older proposal
is supported, so creation order is not approval order.

Reproduction:

1. Generate two previews A and B for the same registrations.
2. Finalize A, retaining newer unapproved B.
3. Complete/cancel the event (the regression also exercises the `IN_PROGRESS` state).
4. Read `/events/{id}/grouping-runs/latest`: before the fix it returns B.

Effect: the organizer's preview panel misrepresents the approved grouping. Stored
final assignments and collaboration history are not overwritten by this read bug.

Fix: prioritize the finalized run in post-finalization/inactive lifecycle states.
Keep explicit run-ID history reads unchanged, and retain the latest proposal when
an event was cancelled before any finalization.

Evidence: new parameterized lifecycle reproduction failed for three states and
passed for `GROUPS_FINALIZED`; the cancelled-without-finalization control passed.
After the fix, grouping/teams/completion regression suite: **50 passed**.
Commit: `f57e7b4`.

### B2 — Automatic schedule calculation underflows a valid datetime

Severity: **Low**. Fixed in `apps/api/app/schemas/events.py`.

Root cause: automatic grouping calculated `start_at - 3 days` before clamping it
to registration close. A valid early date underflows Python's datetime range and
raises `OverflowError` instead of returning a validated draft.

Reproduction: as an organizer, create a draft with registration opening
`0001-01-01T00:00:00Z`, closing at noon, start `0001-01-02T12:00:00Z`, end
`0001-01-03T12:00:00Z`, confirmation `0001-01-02T00:00:00Z`, and no explicit
grouping time. The valid draft request previously raised an unhandled exception
(HTTP 500 in a normal server).

Fix: clamp the lead-time interval to the registration-close/start interval before
subtracting. This preserves the documented later-of-three-days-or-close policy and
does not introduce a new restriction on draft dates.

Evidence: new API reproduction failed with `OverflowError: date value out of range`;
after the fix, event/automation regression suite: **38 passed**. The new test asserts
HTTP 201 and grouping exactly at registration close. Commit: `4271035`.

### B3 — Editing event details silently changes schedule timestamps

Severity: **Medium**.

Root cause: `event-form.tsx` displayed every saved timestamp using
`toISOString().slice(0, 16)`, dropping seconds/fractions, and then submitted all six
schedule fields on any edit. A title-only save therefore overwrote exact database
timestamps with minute-rounded values.

Reproduction: create a draft through the API with seconds and microseconds in each
schedule field, open its organizer form, change only the title, save, and re-read
the event through the API. All untouched timestamps should be identical.

Fix: display seconds/milliseconds using `step="any"`; compare the submitted
instant with the existing value at JavaScript's precision and retain the original
API string for unchanged fields. This preserves PostgreSQL microseconds while
allowing intentional time edits.

Evidence: the browser reproduction read back `2099-02-10T12:00:00Z` instead of
`2099-02-10T12:00:31.123456Z` before the fix. Afterwards,
`event-schedule.spec.ts`: **1 passed**, asserting all six exact timestamps and a
subsequent intentional start-time change. Fixtures include fractional microseconds
that JavaScript cannot represent. Regression tests were split by bug after the red
run; no failing assertions were removed.
Commit: `aab29df`.

### B4 — Recovered schedule request retains an obsolete error

Severity: **Low**.

Root cause: the `GroupingSchedule` effect updated job data after a successful
request without clearing its previous error. An event version change retries
automatically, unlike the manual refresh action that already clears the error.

Reproduction: make the first grouping-job read return HTTP 503; publish the draft
to change its version; let the automatic second read succeed. The panel previously
showed both the recovered job status and the old error.

Fix: after a successful job read, clear the previous error inside the existing
active-request guard. Manual refresh, cancellation guards and request dependencies
are unchanged.

Evidence: the production red test observed `WAITING` alongside the obsolete error
(`Expected: 0`, `Received: 1` alerts). The corrected sustained-outage regression,
`schedule-recovery.spec.ts`, passed against the fresh production build:
**1 passed (30.5s)**.
Commit: `85ac6ce`.

### B5 — Vendored skill formatting blocks repository CI

Severity: **Medium**. Fixed in `.prettierignore`.

Root cause: `npm run format:check` recursively includes installed `.agents/skills`
Markdown. Fourteen downloaded Neon skill files use upstream formatting that does
not match this application's Prettier settings. CI invokes the same check before
lint/tests/build, so a clean checkout fails there.

Reproduction: `node_modules/.bin/prettier --check .agents/skills` exited **1** with
`Code style issues found in 14 files`. The baseline full command also reported
three files in the pre-existing untracked local `demo/` directory.

Fix: ignore only installed `.agents/skills` in application formatting. Do not
reformat downloaded instructions or ignore application source files.

Regression: `git ls-files -z | xargs -0 node_modules/.bin/prettier --check
--ignore-unknown` exited **0**: `All matched files use Prettier code style!`.
Commit: `5a3bfe0`.

### B6 — Existing browser mocks intercept the obsolete API origin

Severity: **Medium** (broken regression coverage/CI).

Root cause: the browser API base moved to same-origin `/api`, but mocked organizer
attention, activity and approval tests still intercepted `http://127.0.0.1:8000/**`.
Browser interception cannot see the server-side Next proxy's upstream request.
The real unauthenticated `/api/me` request therefore reaches the backend, and
tests render the signed-out screen instead of their organizer fixtures. The real
roster test also targeted the old origin when injecting a details-refresh failure.

Reproduction: run the existing browser suite with its configured
`NEXT_PUBLIC_API_URL=/api`. Attention/activity tests fail waiting for their mocked
alert; the page snapshot shows “Sign in to manage events.”

Fix: intercept browser-visible `**/api/**` requests, remove `/api` before matching
the existing mocked endpoint paths, and target the real roster's injected failure
at `**/api/organizer/events/{id}`. Direct backend API clients still use port 8000.
All existing authorization, pagination, approval, retry and saved-change assertions
are retained.

Evidence after the fix: **5 passed, 1 failed**. The roster test now passes its
intended saved-change/failed-refresh checks and reaches completion, where a separate
ambiguous selector fails (B7). Commit: `c6c106c`.

### B7 — Roster browser test selects duplicate dashboard titles

Severity: **Low** (repeat-run regression test failure).

Root cause: after completing an event, the roster test selected its dashboard link
by title across the entire page. The event dashboard also displays public event
discovery, and event titles are not unique. A retained published event from a
previous run can share the completed registration's title.

Reproduction: retain another public event titled `Lifecycle browser workshop`,
then run `teams.spec.ts`. Near completion, the global title selector matches both
the public catalog link and the participant registration link. Playwright reports
`strict mode violation` and two distinct event URLs.

Fix: scope the existing title selector to the `Your registrations` region. Keep
the subsequent exact event-URL, completed-state and read-only roster assertions.
No application behavior or title uniqueness rule is changed.

Regression on the same retained database: `teams.spec.ts`: **1 passed (1.8m)**,
including finalization, confirmation, decline, replacement, reassignment, CSV
export and completion. Commit: `bdd2e54`.

## Verification record

Initial API baseline: `uv run pytest -q` with `RAPO_TEST_DATABASE_URL` set to the
isolated local test database: **194 passed**, one existing Starlette/httpx
deprecation warning. Baseline lint and production build passed.

Backend red reproductions:

```text
uv run pytest -q apps/api/tests/test_grouping.py apps/api/tests/test_events.py \
  -k 'latest_keeps_approved or cancelled_event_without or lower_bound'
4 failed, 2 passed, 32 deselected
```

After B1:

```text
uv run pytest -q apps/api/tests/test_grouping.py apps/api/tests/test_teams.py \
  apps/api/tests/test_event_completion.py
50 passed
```

After B2:

```text
uv run pytest -q apps/api/tests/test_events.py apps/api/tests/test_automation.py
38 passed
```

Full backend regression after both fixes: **200 passed**, including registration
contention, competing finalization/completion, reset/login races, worker rollback,
privacy and migration coverage. Ruff lint/format and mypy also passed.

On the isolated browser-test database, `alembic upgrade head` succeeded and
`alembic check` returned `No new upgrade operations detected.`

The initial production-browser run, including the two new reproductions, returned
**13 passed, 8 failed**. Six existing failures were the stale interception paths
described in B6, and two were B3/B4's new reproductions. This run used one worker
and a temporary Playwright configuration with the production frontend (`npm run
start`) instead of the default development server; test cases and API/mail
configuration were otherwise unchanged.

Individual frontend checks used the webpack development server for hot reload.
The first manually launched targeted test raced API startup and failed with
`ECONNREFUSED 127.0.0.1:8000`; this was a test setup failure, not a behavioral
reproduction. Once ready, B3's targeted check passed. Cold organizer compilation
also exceeded a 50-second warm-up curl timeout before the browser check succeeded.
The initial development run of B4's fixture also failed to observe its injected
one-request outage: Strict Mode replays the initial effect, and the following
successful read cleared it. The fixture now sustains the outage until observed,
then restores service; the original recovery assertions are unchanged.
The next development attempt still reproduced B4 because the filesystem watcher
served an old compiled component. Inspection of
`.next/dev/static/chunks/app/organizer/events/[id]/page.js` showed the old
`if (active) setJob(result)` implementation despite the corrected source. A shell
`touch` did not refresh it. The development server was stopped; final verification
uses a fresh production build. No watcher workaround was added to app configuration.

Final verification:

| Check                                                                       | Result                                                                                                                                                          |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full backend: `uv run pytest -q`                                            | **200 passed**, no skipped tests; one existing deprecation warning.                                                                                             |
| Full browser: `npm run test:e2e -- --config /tmp/rapo-debug-e2e.config.cjs` | **21 passed (4.2m)**, two workers, zero retries. Reused the fresh production frontend; the test runner started an API with the loopback TLS mail configuration. |
| Production build: `npm run build`                                           | Exit 0; `Compiled successfully in 34.4s`, TypeScript passed, static pages generated successfully.                                                               |
| `npm run lint` / `npm run typecheck`                                        | Exit 0.                                                                                                                                                         |
| `uv run ruff check .` / `uv run ruff format --check .`                      | Passed.                                                                                                                                                         |
| `uv run mypy`                                                               | `Success: no issues found in 39 source files`.                                                                                                                  |
| `alembic upgrade head` / `alembic check`                                    | Local test migrations succeeded; `No new upgrade operations detected.`                                                                                          |
| Tracked-file Prettier check and explicit report check                       | `All matched files use Prettier code style!`                                                                                                                    |
| Repository-wide `npm run format:check`                                      | Still exits 1 exclusively for untracked local `demo/` files; downloaded skill formatting no longer blocks the clean checkout.                                   |
| `git diff --check`                                                          | Passed.                                                                                                                                                         |

The complete final browser run includes account persistence, organizer event
management, dashboard filtering/sorting/pagination, registration/capacity/waitlists,
history-aware proposals and retry handling, scheduled grouping, private
notifications, approval feedback, roster repairs, CSV export, completion,
timestamp preservation and error recovery. Reset delivery was tested through the
local TLS SMTP capture, not Gmail.

To rerun the committed tests, create a disposable PostgreSQL database whose name
ends in `_test`, and set `RAPO_DATABASE_URL`, `RAPO_TEST_DATABASE_URL` and
`RAPO_MIGRATION_DATABASE_URL` to its URL. The explicit migration setting also
overrides any inherited provider direct-connection alias. Do not load production
environment files for this test setup. Then run:

```sh
uv run alembic upgrade head
uv run alembic check
uv run pytest -q
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

The last command uses the committed development-server configuration. This audit's
temporary production configuration instead used `npm run start`, two workers,
zero retries and temporary artifact directories, with the same test cases and
loopback API/mail settings. Retained database fixtures were deliberately reused
to verify repeat-run behavior.

## Alignment and change review

The fixes preserve organizer approval, immutable proposal history, final roster
integrity, documented schedule ordering and server-owned state transitions. They
add no features, dependencies, migrations or public API contract changes. Added
tests cover the missing lifecycle/date/precision/recovery cases; existing tests
retain their assertions. Security review found no additional reproducible
privilege escalation, token exposure or participant-data access bypass in the
tested paths. Passing tests do not establish the absence of all vulnerabilities.

## Limits and remaining checks

This is a reproducible local audit, not a production security certification. No
production database, hosted smoke test, real Gmail inbox, Vercel project settings,
Neon provisioning or scheduled GitHub execution was changed/tested. The opt-in
hosted suite requires dedicated smoke credentials and deliberately mutates hosted
test data; it is outside this isolated audit.

The default local formatting command may still warn about the user-owned untracked
`demo/` files; they are not part of the clean-checkout CI failure or these fixes.
The existing Starlette/httpx deprecation warning remains; dependencies were not
changed merely to suppress it.
The browser harness also warned about its temporary `SSL_CERT_FILE` before the
SMTP fixture created that certificate; the subsequent TLS reset journey passed.
