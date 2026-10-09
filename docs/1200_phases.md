# rapo. — Development Phases

**Pace:** ~1–2 hours/day, 5–6 days/week. **Target:** 8 weeks for a solid MVP; add 2–3 weeks buffer for deployment, debugging, and polish. Build vertically, not all frontend then all backend.

## Phase 0 — Scope and foundations (Days 1–3)
**Goal:** Clear requirements and running development environment.

- [ ] Review `1000_requirement.md` and resolve open decisions.
- [ ] Create monorepo, Next.js web app, FastAPI API, local PostgreSQL with Docker Compose.
- [ ] Configure formatting, linting, TypeScript checks, Python type checking, and CI.
- [ ] Implement `/health` endpoint and frontend API connectivity.

**Deliverable:** Frontend and backend run locally; first CI workflow passes.
**Exit test:** Browser fetches live API health JSON.

## Phase 1 — Authentication and event management (Week 1–2)
**Goal:** Real users can create and discover events.

- [ ] Design SQLAlchemy models and first Alembic migration.
- [ ] Register/login/logout and session security.
- [ ] Organizer ownership and role checks.
- [ ] Create/edit/publish event APIs with timezone and date validation.
- [ ] Build landing page, event list, event detail, organizer create/edit form.
- [ ] Add backend authorization and validation tests.

**Deliverable:** Organizer publishes an event; participant can browse it.
**Exit test:** Non-owner cannot edit another organizer's event.

## Phase 2 — Registration and waitlist (Week 3)
**Goal:** Participants can join events without race conditions.

- [ ] Registration with uniqueness and eligibility checks.
- [ ] Fixed capacity and unlimited capacity modes.
- [ ] FIFO waitlist and cancellation/promotion.
- [ ] Participant registration status dashboard.
- [ ] Tests for concurrent registrations, duplicate requests, and promotion.

**Deliverable:** Registration-to-waitlist flow works end-to-end.
**Exit test:** Last available seat cannot be assigned twice under simultaneous requests.

## Phase 3 — Grouping engine (Weeks 4–5)
**Goal:** Generate feasible, repeat-aware team proposals.

- [ ] Derive pair collaboration frequencies from completed teams.
- [ ] Implement feasibility and valid team-size partition logic.
- [ ] Build baseline random assignment and score it.
- [ ] Implement seeded greedy grouping and swap/move improvement.
- [ ] Handle everyone-worked-with-everyone and partial-overlap cases.
- [ ] Store proposal, score, seed, and per-team explanations.
- [ ] Add property-based and hand-calculated unit tests.
- [ ] Build organizer grouping preview UI.

**Deliverable:** Organizer sees proposed teams and why they were chosen.
**Exit test:** Every generated team satisfies size limits, with no missing or duplicated eligible users; infeasible cases are explained.

## Phase 4 — Finalization, confirmation, dropouts (Week 6)
**Goal:** Convert proposals into dependable real assignments.

- [ ] Transactional finalization and stale-proposal checks.
- [ ] Participant confirmation and decline.
- [ ] Withdrawal before/after grouping.
- [ ] Waitlist replacement and `NEEDS_ATTENTION` state.
- [ ] Manual organizer reassignment with validation and audit trail.
- [ ] Final roster and CSV export.
- [ ] End-to-end tests for dropout and replacement paths.

**Deliverable:** Full event lifecycle from registration through confirmation.
**Exit test:** Withdrawals never create silent invalid teams or duplicate assignments.

## Phase 5 — Automation and deployment (Week 7)
**Goal:** A stable, publicly usable demo.

- [ ] Implement scheduled due-event processing with DB-backed locking/idempotency.
- [ ] In-app notifications for key status changes.
- [ ] Deploy PostgreSQL, API, worker, and frontend.
- [ ] Configure production environment variables, HTTPS, CORS, health checks.
- [ ] Run migrations and seed safe demo data.
- [ ] Configure CI checks and verify rollback/backup instructions.

**Deliverable:** Live URL with persistent data and working grouping job.
**Exit test:** Scheduled grouping creates one proposal even if the worker retries.

## Phase 6 — Polish, measurement, portfolio packaging (Week 8)
**Goal:** Make the project interview-ready.

- [ ] Improve responsive layout, loading/empty/error states, and keyboard accessibility.
- [ ] Add audit log view and clear grouping explanations.
- [ ] Benchmark algorithm against random baseline on seeded datasets.
- [ ] Measure API response times and grouping latency at target load.
- [ ] Add screenshots, short walkthrough video, architecture diagram, and API examples.
- [ ] Write README with live link, demo credentials, setup, design decisions, limitations.
- [ ] Perform manual smoke test on desktop and mobile.

**Deliverable:** Resume-ready project with live demo, evidence, and documentation.
**Exit test:** A reviewer can use the demo without needing setup help.

## Weekly cadence
- **Day 1:** Choose one user-facing slice and acceptance test.
- **Days 2–4:** Implement API, database, and UI for that slice.
- **Day 5:** Add automated tests and edge cases.
- **Day 6:** Refactor, document, deploy preview, and record learnings.
- **Day 7:** Rest or catch up.

## Milestone tracker
| Milestone | Expected week | Proof |
|---|---:|---|
| M1: Auth + events | 2 | Organizer creates published event |
| M2: Registration + waitlist | 3 | Concurrent capacity test passes |
| M3: Valid grouping previews | 5 | Score report and invariant tests |
| M4: Confirmations + dropouts | 6 | E2E lifecycle test passes |
| M5: Public deployment | 7 | Live URL, working worker, seeded demo |
| M6: Portfolio-ready release | 8 | README, video, benchmarks, CI green |

## Scope control
**Must ship:** Authentication, events, registration, waitlist, history-aware grouping, preview/finalize, confirmation/withdrawal, tests, deployment.

**Can defer:** Email, calendar sync, analytics dashboards, AI explanations, exact optimization for large groups, payment flows, organization billing.

## First task — Start here
1. Create `rapo/apps/web` and `rapo/apps/api`.
2. Run PostgreSQL locally with Docker Compose.
3. Implement FastAPI `GET /health` returning `{ "status": "ok" }`.
4. Render that response in a Next.js page.
5. Commit as `chore: bootstrap rapo web api and database`.

**Questions to answer after completing it:** Why are frontend and API on separate ports? How does the browser call the API? What does CORS protect? Why keep DB credentials only on the server?
