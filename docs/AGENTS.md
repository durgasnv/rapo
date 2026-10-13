# AGENTS.md — rapo. Development Rules

## 1. Purpose

These instructions govern AI coding agents working on rapo., a planned web platform for event registration and fair, history-aware team formation. The goal is not merely working code: the developer must understand why each feature exists, how frontend and backend communicate, how data changes, and how to diagnose failures.

> **Guiding principle:** Build slowly. Explain clearly. Change one thing at a time.

## 2. Project context and source of truth

Read these files before proposing implementation:

- [1000_requirement.md](1000_requirement.md): product rules, event lifecycle, constraints, edge cases, acceptance criteria.
- [1100_plan.md](1100_plan.md): architecture, data model, API contracts, grouping approach, deployment.
- [1200_phases.md](1200_phases.md): phased scope and milestones.

If documents disagree, identify the conflict and ask the developer to resolve it. Do not silently invent product policy. If these files are missing, ask for them rather than assuming requirements.

### Core technology

- Frontend: Next.js, React, TypeScript, Tailwind CSS.
- Backend: Python, FastAPI, Pydantic.
- Persistence: PostgreSQL, SQLAlchemy, Alembic.
- Grouping: isolated Python domain logic; use a heuristic initially, introduce optimization libraries only when justified.
- Background processing: scheduled worker with database-backed idempotency.
- Deployment: HTTPS frontend, API, worker, and managed PostgreSQL.

Prefer a modular monolith over microservices. Never add AI/LLMs, graph databases, queues, or third-party services without a demonstrated requirement and developer approval.

## 3. Before implementing any non-trivial change

Do not immediately write code. First provide a short proposal explaining:

1. What the organizer or participant will experience.
2. What will happen internally, from UI through API to database or grouping engine.
3. Which files, models, endpoints, migrations, and dependencies will change.
4. Assumptions, failure cases, security implications, and possible side effects.
5. How the change will be tested.

Ask: “Is this the behavior you want me to implement?” Wait for confirmation before modifying code. Clarify ambiguous business rules instead of guessing. Once confirmed, implement only the agreed slice; do not repeatedly request approval for trivial steps within that slice.

## 4. Learning-first workflow

For each confirmed feature:

1. Inspect existing code and identify the relevant boundaries.
2. Explain the smallest useful implementation and why it fits the architecture.
3. Implement the feature without unrelated refactoring.
4. Run targeted tests and explain the results.
5. Document meaningful behavior and trade-offs.
6. Review the full implementation diff against the approved scope, product requirements, lifecycle rules, architecture, and privacy boundaries.
7. Review for bugs, unnecessary changes, missing tests, security issues, and breaking changes. Fix findings within the approved scope and rerun relevant checks before calling the feature complete. Report unresolved findings and limitations honestly; do not silently expand scope to unrelated work.
8. Document the review findings and verification evidence alongside the feature explanation.
9. Make one focused Conventional Commit when repository access and authorization allow.
10. Summarize what changed, how to try it, how it was implemented, and what the alignment/bug review found.

Favor small, understandable functions and explicit contracts. Give the developer a brief explanation of unfamiliar Python, SQLAlchemy, Next.js, or algorithm concepts. When appropriate, include a debugging question or small exercise rather than hiding all reasoning in generated code.

## 5. Commit rules

Use a single-line Conventional Commit for each coherent, independently testable change. Do not combine unrelated features. Examples:

```text
feat: add event registration endpoint
feat: implement collaboration history scoring
fix: prevent duplicate event registrations
test: cover infeasible team size constraints
docs: explain team grouping lifecycle
chore: configure alembic migrations
```

Do not invent commit hashes or claim a commit occurred if it did not. Do not add AI-agent co-author or attribution trailers. Do not rewrite existing history without explicit permission.

## 6. Documentation is part of implementation

Significant features require `docs/features/<feature>.md`, where appropriate, describing:

- Purpose and user experience.
- Internal flow and relevant frontend, API, service, and database components.
- Data validation and authorization.
- Design reasoning and alternatives.
- Failure, retry, and recovery behavior.
- Tests, limitations, and future extensions.

Create conceptual documentation for non-obvious workflows under `docs/concepts/`, such as:

```text
docs/
  features/
    authentication.md
    event-registration.md
    waitlist.md
    group-confirmation.md
    withdrawals.md
  concepts/
    event-lifecycle.md
    grouping-algorithm.md
    collaboration-history.md
    grouping-scheduling.md
    transaction-and-concurrency.md
```

Do not generate empty placeholder documentation. Update existing docs rather than duplicating them. Explain why an approach was chosen, not just what code does.

## 7. Scope boundaries

Follow [1200_phases.md](1200_phases.md) and the current milestone. Do not build future features opportunistically.

- Foundation: project setup, database, migrations, auth, roles.
- Event workflows: organizer events, registration windows, capacity, waitlists.
- Grouping: eligibility, feasibility checks, history-aware assignment, previews, finalization.
- Lifecycle: confirmations, withdrawals, replacements, administrative controls.
- Release: scheduled grouping, notifications, testing, monitoring, deployment.

These are workstreams, not replacements for the detailed schedule in [1200_phases.md](1200_phases.md). Keep advanced optimization, analytics, and integrations out of the MVP unless approved.

## 8. rapo. business rules

Treat the product documents as authoritative. In particular:

- Enforce role-based access: participant actions must not gain organizer/admin privileges.
- Support both fixed-capacity and uncapped events with minimum/maximum team-size constraints.
- Respect event timezone, registration windows, grouping eligibility, and lifecycle status.
- The scheduled grouping target defaults to three days before event start, but cannot run before registration closes; validate the schedule.
- Do not silently create invalid teams or assign one participant to multiple teams in the same finalized grouping.
- Minimize repeated pairings using historical collaboration; when zero-repeat grouping is impossible, prefer the lowest-history-cost valid assignment and explain the compromise.
- Clearly distinguish hard constraints (must hold) from soft objectives (optimize when feasible).
- Infeasible inputs must produce actionable explanations, not invented teams.
- Keep proposed groupings separate from finalized groupings. Organizer approval is required for finalization.
- Respect withdrawal, confirmation, waitlist, and replacement policies in [1000_requirement.md](1000_requirement.md).
- Admin overrides must be authorized, audited, and unable to bypass hard constraints silently.

Never claim the grouping heuristic produces the global optimum unless that property is actually proven.

## 9. Algorithm rules

Implement the grouping engine as testable Python logic, independent of HTTP handlers and database sessions where practical.

Document:

1. Input participants, historical pair counts, and event constraints.
2. Feasibility validation before optimization.
3. Cost/scoring function and treatment of repeated teammates.
4. Deterministic tie-breaking or stored random seed for reproducibility.
5. Runtime limits, fallback behavior, and quality metrics.
6. Why the chosen algorithm is appropriate for the current event sizes.

Test zero-history events, odd participant counts, exact capacities, impossible size ranges, heavily overlapping histories, and a participant who has worked with everyone. Measure repeat-pair scores against a simple baseline rather than claiming fairness without evidence.

## 10. Database integrity and concurrency

- Use Alembic migrations for schema changes; do not rely on implicit schema creation in production.
- Add foreign keys, uniqueness constraints, indexes, and appropriate check constraints.
- Enforce one active registration per user per event as specified by the data model.
- Handle concurrent last-seat registrations and waitlist promotions atomically.
- Make grouping scheduling, preview creation, and finalization idempotent or safely retryable.
- Finalize teams transactionally; prevent two competing grouping runs from both becoming final.
- Keep audit records for grouping triggers, finalizations, overrides, and cancellations.
- Do not silently delete historical collaboration needed for future assignments.

Explain transaction boundaries and race conditions whenever implementing these flows.

## 11. Authentication, security, and privacy

Apply least privilege and collect only information required for events and team formation.

- Protect authenticated routes and enforce authorization on the backend, not only in UI components.
- Validate inputs and guard against injection, mass assignment, and insecure object access.
- Store passwords securely if password authentication is used; do not log tokens, passwords, or secrets.
- Use environment variables or a secret manager; never commit `.env` secrets.
- Restrict participant access to others' private profiles and collaboration history; expose only the information needed for their role.
- Do not disclose sensitive historical pairing details in public explanations.
- Document retention/deletion behavior for registrations, profiles, and history.
- Apply CORS, HTTPS, rate limits, and secure cookie/token handling as appropriate.

No surveillance, external scraping, or unrelated personal-data collection.

## 12. Testing requirements

Every meaningful feature must include appropriate verification:

- Unit tests: validation, event transitions, grouping feasibility and scoring.
- Integration tests: API + database behavior, authentication, migrations, transactions.
- End-to-end tests: create event → register → group preview → finalize → confirm → withdraw/replace.
- Concurrency tests: final available seat, duplicate registration, competing finalizations.
- Security tests: participant attempts organizer-only actions or accesses another event's private data.
- Failure tests: worker retry, partial database failure, invalid configuration, notification failure.

Use representative fixtures. Do not claim tests passed unless they actually ran; report skipped tests and blockers. Document manual verification where automated tests are impractical.

## 13. Code quality and comments

Keep API routers thin, business rules in services/domain modules, persistence in clearly defined data-access boundaries, and frontend state distinct from authoritative backend state. Prefer readable types, explicit validation, and useful errors.

Comments should explain non-obvious constraints and reasoning, not narrate obvious syntax. Example:

```python
# Persist the seed so organizers can reproduce and audit a grouping preview.
```

Avoid premature abstractions, duplicated business logic, and unrelated dependency additions.

## 14. Deployment and recovery

Before declaring a feature production-ready:

- Verify configuration and secrets in the deployment environment.
- Apply migrations safely and maintain rollback/backup procedures.
- Verify HTTPS, health checks, and database connectivity.
- Ensure scheduled jobs can restart without double-grouping an event.
- Log actionable errors without exposing private participant data.
- Verify the real deployed user journey, not only localhost.
- Document known limits and operational costs.

Never perform destructive production migrations or delete user data without explicit approval and a recovery plan.

## 15. Agent communication

After each change, report concisely:

1. What changed and why.
2. Which files were touched.
3. How the request travels through the system.
4. Tests actually executed and their results.
5. Documentation updated.
6. Commit message/hash, only if a commit was actually made.
7. Any remaining risks or developer exercises.

Avoid large unexplained code dumps. The developer should be able to modify the feature independently after the explanation.

## 16. Definition of done

A feature is complete only when:

- [ ] The approved behavior works end to end for its intended scope.
- [ ] Role checks, validation, and relevant database constraints are enforced.
- [ ] Important success, edge, and failure paths are tested.
- [ ] User-visible errors are actionable.
- [ ] Meaningful technical decisions and flows are documented.
- [ ] No unrelated or future-phase features were added.
- [ ] The final diff was reviewed for project alignment, bugs, unnecessary changes, missing tests, security issues, and breaking changes.
- [ ] Findings within the approved scope were fixed and relevant checks rerun; remaining findings and limitations were reported.
- [ ] A focused Conventional Commit exists if committing was authorized and available.
- [ ] The developer can explain what the feature does and why.

Build slowly. Explain clearly. Change one thing at a time.
