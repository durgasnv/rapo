# rapo. — Development Phases

**Pace:** ~1–2 hours/day, 5–6 days/week. **Target:** 8 weeks for a solid MVP; add 2–3 weeks buffer for deployment, debugging, and polish. Build vertically, not all frontend then all backend.

## Phase 0 — Scope and foundations (Days 1–3)

**Goal:** Clear requirements and running development environment.

- [ ] Review `1000_requirement.md` and resolve open decisions.
- [x] Create monorepo, Next.js web app, FastAPI API, local PostgreSQL with Docker Compose.
- [x] Configure formatting, linting, TypeScript checks, Python type checking, and CI.
- [x] Implement `/health` endpoint and frontend API connectivity.

**Deliverable:** Frontend and backend run locally; first CI workflow passes.
**Exit test:** Browser fetches live API health JSON.

**Implementation status:** Foundation implemented. API and live-browser health/retry
tests pass; PostgreSQL health and a test query passed locally on port 55432.
Formatting, lint, types, and a production build passed, including checks from a
fresh checkout under `/tmp` to avoid slow Windows-mounted filesystem reads.
CI is configured; its first hosted run is pending. Product-policy decisions in
the requirements remain open and must be resolved before the affected features.

## Phase 1 — Authentication and event management (Week 1–2)

**Goal:** Real users can create and discover events.

- [x] Design SQLAlchemy models and first Alembic migration.
- [x] Register/login/logout and session security.
- [x] Organizer ownership and role checks.
- [x] Create/edit/publish event APIs with timezone and date validation.
- [x] Build landing page, event list, event detail, organizer create/edit form.
- [x] Add backend authorization and validation tests.

**Deliverable:** Organizer publishes an event; participant can browse it.
**Exit test:** Non-owner cannot edit another organizer's event.

**Implementation status:** Phase 1 flow implemented and exercised against
PostgreSQL and a live browser. Organizer access is granted through a trusted
server command. Published events are read-only in this slice; schedule inputs use
UTC and public details use the configured timezone. Email password reset is
implemented; SMTP setup and real delivery verification are required before release.
Hosted CI/deployment has not been run in this session.

**Recovery checkpoint (2026-10-10):** Restored locked Python dependencies and
verified with the installed Node.js 24 runtime. All 26 API tests passed against an
isolated PostgreSQL 16 test database. Python lint, formatting, and type checks,
frontend formatting/lint/type checks, and Alembic schema comparison passed.
The production frontend build and all four live-browser tests also passed from a
fresh Linux checkout using the locked npm dependencies and matching Chromium.
Docker Desktop WSL integration is unavailable in this environment; verification
used a temporary PostgreSQL cluster rather than the existing application data.
Phase 2 is the next implementation milestone.

## Phase 2 — Registration and waitlist (Week 3)

**Goal:** Participants can join events without race conditions.

- [x] Registration with uniqueness and eligibility checks.
- [x] Fixed capacity and unlimited capacity modes.
- [x] FIFO waitlist and cancellation/promotion.
- [x] Participant registration status dashboard.
- [x] Tests for concurrent registrations, duplicate requests, and promotion.

**Deliverable:** Registration-to-waitlist flow works end-to-end.
**Exit test:** Last available seat cannot be assigned twice under simultaneous requests.

**Implementation status (2026-10-10):** Phase 2 implemented and verified with
41 PostgreSQL-backed API tests (15 new registration tests, including five
concurrency cases) and six live-browser tests. Migration/schema comparison,
formatting, lint, both type checkers, and the production frontend build passed.
Registration closes at its configured cutoff; self-service withdrawal and FIFO
promotion stop at the scheduled grouping time. Rejoining takes a new queue ticket.
Participant dashboards and private organizer rosters are paginated and refresh
on request. Cancelled events remain visible in participants' own history.
Verification used an isolated PostgreSQL 16 database and a Linux checkout with
locked dependencies. Hosted CI/deployment remains unverified. The Phase 3 checkpoint below records
grouping previews; notifications and post-grouping replacements remain later work.

## Phase 3 — Grouping engine (Weeks 4–5)

**Goal:** Generate feasible, repeat-aware team proposals.

- [x] Derive pair collaboration frequencies from completed teams.
- [x] Implement feasibility and valid team-size partition logic.
- [x] Build baseline random assignment and score it.
- [x] Implement seeded greedy grouping and swap/move improvement.
- [x] Handle everyone-worked-with-everyone and partial-overlap cases.
- [x] Store proposal, score, seed, and per-team explanations.
- [x] Add property-based and hand-calculated unit tests.
- [x] Build organizer grouping preview UI.

**Deliverable:** Organizer sees proposed teams and why they were chosen.
**Exit test:** Every generated team satisfies size limits, with no missing or duplicated eligible users; infeasible cases are explained.

**Implementation status (2026-10-10):** Phase 3 implemented with owner-only
manual previews after registration closes, completed-event pair history, balanced
team-size selection, seeded greedy/swap/move search, fairness tie-breaking,
persistent input snapshots, and stale/retry handling. The engine supports at most
100 eligible participants and bounds search work deterministically. Existing
withdrawal/promotion remains available before the scheduled grouping cutoff.
Finalization/completion APIs and scheduled generation remain in later phases;
completed historical memberships are exercised through trusted test fixtures.

Verification passed: 75 backend tests (18 engine and 16 grouping API tests added),
seven live-browser tests, migration/schema comparison, Python/web formatting,
lint, type checks, and the production frontend build. The final snapshot schema
was checked again with the backend suite and targeted grouping browser flow.
Tests used isolated PostgreSQL 16 databases and separate browser-server ports.
A seeded 100-person benchmark took about 0.07 seconds with sizes 3–5 and 0.92
seconds with sizes 50–100 on this machine; these are engine measurements, not API
latency guarantees. Hosted CI/deployment remains unverified. Phase 4 is next.

## Phase 4 — Finalization, confirmation, dropouts (Week 6)

**Goal:** Convert proposals into dependable real assignments.

- [x] Transactional finalization and stale-proposal checks.
- [x] Participant confirmation and decline.
- [x] Withdrawal before/after grouping.
- [x] Waitlist replacement and `NEEDS_ATTENTION` state.
- [x] Manual organizer reassignment with validation and audit trail.
- [x] Final roster and CSV export.
- [x] End-to-end tests for dropout and replacement paths.

**Deliverable:** Full event lifecycle from registration through confirmation.
**Exit test:** Withdrawals never create silent invalid teams or duplicate assignments.

**Implementation status (2026-10-10):** Phase 4 implements separate final teams
and assignments, atomic freshness-checked finalization, private team confirmation,
decline and withdrawal, explicit FIFO replacements, validated moves/swaps,
continuation approval, deadline extension, audit snapshots, and owner CSV export.
Missed deadlines keep members pending and flag attention. Teammate changes reset
confirmations; withdrawals before finalization now remain open until event start.
The approved preview stays unchanged beside the current roster.

Verification passed: 91 backend tests (16 new lifecycle tests), eight live-browser
tests, migration/schema comparison, Python/web formatting, lint, type checks, and
the production frontend build. Tests used an isolated PostgreSQL database and
separate browser-server ports. Hosted CI and
deployment remain unverified. Event completion was subsequently added as a
focused lifecycle extension; see [event completion](features/event-completion.md).
See [team-lifecycle.md](features/team-lifecycle.md) for behavior and recovery.

## Phase 5 — Automation and deployment (Week 7)

**Goal:** A stable, publicly usable demo.

- [x] Implement scheduled due-event processing with DB-backed locking/idempotency.
- [x] In-app notifications for key status changes.
- [ ] Deploy PostgreSQL, API, worker, and frontend.
- [ ] Configure production environment variables, HTTPS, CORS, health checks.
- [ ] Run migrations and seed safe demo data.
- [ ] Configure CI checks and verify rollback/backup instructions.

**Deliverable:** Live URL with persistent data and working grouping job.
**Exit test:** Scheduled grouping creates one proposal even if the worker retries.

**Automation implementation (2026-10-11):** Added a separate retry-safe worker,
persistent per-event job outcomes, owner-visible scheduling status, and private
in-app notifications with pagination, unread filtering, and read-state persistence.
The worker creates proposals only; organizer approval remains required. Infeasible
inputs are reported, failures back off, and notifications commit with their
associated changes. See [automation and notifications](features/scheduled-grouping-and-notifications.md).
Verification passed: 112 backend tests, nine live-browser tests, worker CLI smoke,
migration/schema comparison, formatting, lint, types, and production build.
Hosting, HTTPS, backups, demo seeding, and deployment verification remain open.

**Organizer attention overview (2026-10-13):** Added an owner-only, paginated
summary on Manage events for proposed groupings, recorded job failures/blocks,
and finalized roster attention reasons. It reuses existing data and remediation
flows without changing grouping policy. See
[organizer-attention.md](features/organizer-attention.md). Deployment remains open.

## Phase 6 — Polish, measurement, portfolio packaging (Week 8)

**Goal:** Make the project interview-ready.

- [ ] Improve responsive layout, loading/empty/error states, and keyboard accessibility.
- [x] Add owner-only event audit log view.
- [ ] Improve grouping explanations for release.
- [ ] Benchmark algorithm against random baseline on seeded datasets.
- [ ] Measure API response times and grouping latency at target load.
- [ ] Add screenshots, short walkthrough video, architecture diagram, and API examples.
- [ ] Write README with live link, demo credentials, setup, design decisions, limitations.
- [ ] Perform manual smoke test on desktop and mobile.

**Deliverable:** Resume-ready project with live demo, evidence, and documentation.
**Exit test:** A reviewer can use the demo without needing setup help.

**Event activity view (2026-10-14):** Added owner-only, paginated audit reads and
an activity panel on Manage event. Existing records are translated into readable
actions with actor names and event-timezone timestamps, without exposing raw
snapshots. See [event-audit.md](features/event-audit.md). Other Phase 6 work and
public deployment remain open.

## Weekly cadence

- **Day 1:** Choose one user-facing slice and acceptance test.
- **Days 2–4:** Implement API, database, and UI for that slice.
- **Day 5:** Add automated tests and edge cases.
- **Day 6:** Refactor, document, deploy preview, and record learnings.
- **Day 7:** Rest or catch up.

## Milestone tracker

| Milestone                    | Expected week | Proof                                 |
| ---------------------------- | ------------: | ------------------------------------- |
| M1: Auth + events            |             2 | Organizer creates published event     |
| M2: Registration + waitlist  |             3 | Concurrent capacity test passes       |
| M3: Valid grouping previews  |             5 | Score report and invariant tests      |
| M4: Confirmations + dropouts |             6 | E2E lifecycle test passes             |
| M5: Public deployment        |             7 | Live URL, working worker, seeded demo |
| M6: Portfolio-ready release  |             8 | README, video, benchmarks, CI green   |

## Scope control

**Must ship:** Authentication, events, registration, waitlist, history-aware grouping, preview/finalize, confirmation/withdrawal, tests, deployment.

**Can defer:** Email, calendar sync, analytics dashboards, AI explanations, exact optimization for large groups, payment flows, organization billing.

## First task — Start here

1. Create `apps/web` and `apps/api` inside the existing repository root.
2. Run PostgreSQL locally with Docker Compose.
3. Implement FastAPI `GET /health` returning `{ "status": "ok" }`.
4. Render that response in a Next.js page.
5. Commit as `chore: bootstrap rapo web api and database`.

**Questions to answer after completing it:** Why are frontend and API on separate ports? How does the browser call the API? What does CORS protect? Why keep DB credentials only on the server?
