# rapo. — Product Requirements

**Version:** 1.0 | **Status:** Proposed MVP | **Product:** Intelligent activity and team formation platform

## 1. Problem and goal
Event organizers struggle to form balanced teams while respecting participant availability, team-size limits, historical collaborations, dropouts, and deadlines. rapo. manages event registration and forms feasible teams that **minimize repeated teammate pairings** while explaining compromises.

**Success:** An organizer can publish an event, accept registrations, preview and finalize valid teams, manage withdrawals, and export results without spreadsheets.

## 2. Roles
- **Visitor:** View public events and sign up/sign in.
- **Participant:** Register, cancel, see status, confirm assigned team, and view relevant history.
- **Organizer/Admin:** Create and manage owned events, configure constraints, trigger/preview/finalize assignments, manage waitlists and overrides, and export teams.
- **Platform Admin (later):** Moderate users and audit system activity.

Authorization is server-enforced; organizers cannot access other organizers' private events.

## 3. Event data and lifecycle
An event includes title, description, organizer, location or online link, timezone, event start/end timestamps, registration open/close timestamps, grouping trigger timestamp, optional capacity, minimum and maximum team size, confirmation deadline, and status.

**Statuses:** `DRAFT → PUBLISHED → REGISTRATION_CLOSED → GROUPING_READY → GROUPS_PROPOSED → GROUPS_FINALIZED → IN_PROGRESS → COMPLETED`; `CANCELLED` may be entered from allowed active states. Admins may trigger grouping manually after registration closes; scheduled grouping is **three days before event start by default**, but if registration closes later than that, grouping waits until registration closes. Validate and display the resulting schedule before publishing.

### Capacity configurations
1. **Fixed participant capacity + flexible team size:** e.g., at most 40 participants, teams of 3–5.
2. **No fixed participant capacity + flexible team size:** unlimited registrations until cutoff, teams of 3–5.

A fixed team size is represented by `min_team_size = max_team_size`. Minimum participants needed to create at least one team is `min_team_size` unless organizer cancels or reschedules.

## 4. Functional requirements
| ID | Requirement | MVP acceptance criterion |
|---|---|---|
| FR-01 | Authentication | Register/login/logout and reset password; hashed passwords and secure sessions |
| FR-02 | Event creation | Organizer can draft, edit, publish, cancel owned events with validated dates/limits |
| FR-03 | Event discovery | Users can browse published events and filter by date/status |
| FR-04 | Registration | Eligible user registers once per event; no duplicates; capacity checked atomically |
| FR-05 | Waitlist | Full fixed-capacity events queue registrations FIFO; promotion after cancellation before grouping |
| FR-06 | Registration cancellation | User can withdraw; event status and waitlist update consistently |
| FR-07 | Collaboration history | Store finalized team membership and derive pair frequencies from completed/eligible prior events |
| FR-08 | Team formation | Produce teams within configured size range when feasible, minimizing repeat pairs |
| FR-09 | Admin preview | Show proposed teams, constraint violations (if any), repeat-pair score, and explanations |
| FR-10 | Finalization | Admin confirms teams; persist assignments transactionally; prevent duplicate finalization |
| FR-11 | Participant confirmation | Members accept/decline assignments before deadline; status visible to organizer |
| FR-12 | Withdrawal after assignment | Organizer sees vacancy and can promote/reassign a waitlisted participant, or approve team continuing if size permits |
| FR-13 | Manual override | Organizer can move participants while preserving hard constraints, with audit log |
| FR-14 | Notifications | In-app status notifications; email notifications optional for MVP |
| FR-15 | Export | Download finalized team roster as CSV |
| FR-16 | Auditability | Record who triggered grouping, finalized, overrode, or cancelled |

## 5. Team formation rules
### Hard constraints
- Every active eligible participant belongs to **at most one** team per event.
- Team sizes must be within `[min_team_size, max_team_size]` for a finalized valid assignment.
- No participant can be placed in a team after withdrawing or declining eligibility.
- Assignments respect any explicitly configured eligibility requirements.
- Grouping/finalization is idempotent; concurrent requests cannot create duplicate teams.

### Soft optimization objectives
1. Minimize repeat pairings across prior completed events.
2. When everyone has previously worked together, prefer combinations with **lowest collaboration frequency**.
3. Among equally good solutions, spread repeat-pair burden fairly across participants.
4. Use deterministic tie-breaking (seed and participant IDs) for reproducible results.

### Feasibility and edge cases
- **Too few people:** Do not generate invalid teams; show unmet minimum and allow reschedule/cancel/wait.
- **Unpartitionable count:** If no partition satisfies team sizes (e.g., 7 people with exactly 4 per team), block finalization and suggest feasible adjustments; do not silently break limits.
- **Partial overlap:** If some prior pairings cannot be avoided, minimize total weighted repeat score and show the unavoidable repeats.
- **Worked with everyone:** Choose the lowest-frequency repeated partnerships, not random pairs.
- **Late withdrawal before finalization:** Re-run grouping on eligible participants.
- **Withdrawal after finalization:** Offer waitlist replacement; otherwise allow organizer to approve continuation only if team size remains valid, or explicitly reopen grouping.
- **No available replacement:** Surface a blocked state and organizer choices; never silently leave an invalid finalized team.
- **Confirmation declines:** Treat as withdrawal from assignment; do not automatically assign to another team without a valid workflow.
- **Simultaneous registrations:** Capacity and waitlist ordering remain correct under concurrency.
- **Event cancellation:** Notify participants; preserve audit records.

## 6. Key screens
1. Landing and public event listing.
2. Sign-in/sign-up.
3. Event detail with registration status and capacity.
4. Participant dashboard (registered/waitlisted/assigned/confirmed).
5. Organizer event creation/editing.
6. Organizer registrations and waitlist management.
7. Grouping preview with score and explanations.
8. Final team roster, confirmations, and replacements.

## 7. Non-functional requirements
- **Security:** RBAC, password hashing, input validation, rate limiting, CSRF protection where applicable, secrets outside source control, HTTPS.
- **Reliability:** Database transactions for registration/finalization; retry-safe scheduled jobs; consistent event state transitions.
- **Privacy:** Minimize stored personal data, restrict visibility of participant details, document retention/deletion policy.
- **Performance:** Pagination; index registration/event queries; target <2s common API response under normal demo load (measure rather than claim).
- **Accessibility:** Keyboard navigation, semantic controls, readable contrast, meaningful status messages.
- **Observability:** Structured logs, error reporting, health endpoint, job outcome logs.
- **Deployment:** Public frontend and backend, persistent managed database, documented environment configuration and demo dataset.

## 8. MVP exclusions
No payments, chat, public social graph, ML-based personality matching, native mobile app, multi-tenant billing, or complex cross-event availability optimization. Email and calendar integrations are later enhancements.

## 9. Release acceptance checklist
- [ ] All critical user flows work end-to-end on the deployed site.
- [ ] Valid configurations produce valid groups; infeasible configurations are explained.
- [ ] Pair-frequency scoring is tested against hand-calculated examples.
- [ ] Registration, withdrawal, and finalization concurrency tests pass.
- [ ] Organizer permissions are verified with negative tests.
- [ ] Users can access a demo event with seeded historical pairings.
- [ ] README includes setup, architecture, API, limitations, screenshots, and live link.

## 10. Open decisions before implementation
- Should the historical collaboration graph include only completed events, or also finalized events that never occurred? **Default: completed only.**
- How long may participants confirm after finalization? **Proposed: organizer-configured deadline.**
- Can organizers force an invalid group size? **Default: no; change event constraints and regenerate instead.**
- What happens if registration cutoff is after the three-day trigger? **Default: run immediately after cutoff.**
