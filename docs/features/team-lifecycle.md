# Final teams, confirmations, and roster repair

Phase 4 turns an organizer-approved preview into real assignments. It adds
participant confirmations/declines, withdrawals until event start, FIFO vacancy
replacement, validated moves/swaps, explicit continuation approval, deadline
extension, and an owner-only CSV export. The [Phase 5 automation slice](scheduled-grouping-and-notifications.md)
adds notifications and scheduled previews; no background task removes people who
miss a deadline.

## Try the flow

1. Apply migrations and sign in as the event owner.
2. After registration closes, generate a preview and choose **Finalize these teams**.
3. Sign in as a registered participant. From **My account**, choose
   **View your team and confirm**. Participants see only their own active team.
4. Confirm or decline before the deadline. Declining removes the assignment and
   registration; withdrawing is also available until event start.
5. The organizer opens **Final team roster** and refreshes to see changes. A
   vacancy or overdue confirmation shows `NEEDS_ATTENTION` with reasons.
6. Fill a vacancy from the FIFO waitlist, approve the current size if valid, or
   make a valid move/swap. A changed roster requires affected teammates to confirm
   again. Extend the confirmation deadline explicitly if more time is needed.
7. Use **Export teams CSV** to download the owner-only roster. It includes retired
   assignments and confirmation states for accountability, without email addresses.

The screens refresh on request. They do not poll, send messages, or silently
finalize/regenerate teams. The original approved preview remains visible beside
the current roster; its score describes that original proposal, not later manual
changes.

## Persistence and transaction boundaries

`FinalTeam` and `Assignment` are separate from proposal `Team` and `TeamMember`
rows. Finalization copies the approved proposal once, marks its run `FINALIZED`,
and transitions the event to `GROUPS_FINALIZED`. Proposal memberships are never
edited by withdrawals, replacements, or reassignment.

Every write locks the same event row used by registration and grouping. Before
finalization, the service checks the event version, current input fingerprint,
complete and unique eligible coverage, team-size limits, capacity, and the
confirmation deadline. Teams, assignments, event state, and audit entry commit
together. Retrying the selected finalized run returns the existing roster;
competing runs cannot both finalize.

Database constraints enforce one assignment row per event/user, one numbered
final team per event, matching event/run and team/event foreign keys, valid
assignment statuses, positive team versions and targets, and one finalized
grouping run per event. Withdrawn and declined rows remain stored; they cannot be
reactivated through reassignment or replacement.

Owner roster writes require `version` and a UUID `request_id`. A `RosterAction`
ledger fingerprints the action and body. Matching retries return current state
without repeating the action. A changed body using the same ID is rejected, and
new actions using stale versions return 409. The browser retains request IDs after
network failures. Audit entries contain before/after assignment IDs, statuses,
team versions/targets, event version, and deadline; they contain no passwords,
session tokens, or email addresses.

## Confirmation and withdrawal policy

- Each active assignment is `PENDING` or `CONFIRMED`. Decline sets `DECLINED`;
  withdrawal sets `WITHDRAWN`. Both retire the registration as `CANCELLED`.
- Confirmation and decline require `now < confirmation_deadline`. Event start
  also closes writes. A repeated already-successful decision is a harmless retry.
- Confirmation requests include the team's version. A changed roster rejects an
  old confirmation instead of accepting consent to previous teammates.
- Replacements, moves, swaps, and withdrawals increment affected team versions
  and reset active teammates to `PENDING`. Confirmation by another member does
  not change the team version.
- Missing the deadline leaves a member pending and flags attention. There is no
  automatic removal, replacement, extension, or assumed consent.
- The owner can extend the deadline strictly later than both its previous value
  and the current time, no later than event start. Extension does not revive
  retired assignments or discard existing confirmations.
- **Phase 4 changes the earlier Phase 2 withdrawal cutoff:** before finalization,
  withdrawal and automatic FIFO promotion remain available until event start,
  including after the scheduled grouping time. Existing previews then become
  stale. After finalization, withdrawal creates a visible vacancy and promotion
  requires an explicit owner action. Waitlisted users may also withdraw.
- Cancellation preserves assignments/audits and disables roster writes.

## Repair rules

Team status is derived from the current roster and clock, so overdue pending
confirmations are visible even without a worker:

| Status                   | Meaning                                                              |
| ------------------------ | -------------------------------------------------------------------- |
| `READY`                  | Valid size, no unresolved vacancy, and every active member confirmed |
| `AWAITING_CONFIRMATIONS` | Valid roster with pending confirmations before the deadline          |
| `NEEDS_ATTENTION`        | Invalid size, unresolved vacancy, or overdue pending confirmation    |

The target size starts as the approved proposal's size. A dropout leaves that
target intact. **Fill vacancy from waitlist** chooses the lowest queue ticket
among waiting users without an existing assignment, requires an available vacancy
and open confirmation window, and never exceeds the maximum size. Retrying cannot
claim another person. If no eligible waiting user exists, the API explains that.

**Approve current team size** changes its target only when the active count meets
the event's hard size limits. It does not waive overdue confirmations. Empty or
undersized teams remain blocked; the organizer must repair them, extend the
deadline when necessary, or cancel the event.

Each team card shows its active count, target size, and allowed size range.
Attention reasons include a keyword and current counts: **Below minimum**,
**Above maximum**, **Vacancy**, or **Confirmation overdue**. Approval is disabled
when the count is outside the allowed range or there is no outstanding vacancy;
nearby text explains the restriction. Disabled approval uses muted text and a
normal cursor so it does not look like an in-progress request. The API continues
enforcing size limits independently of the browser.

Approval and replacement show success or failure on the affected card. A valid
continuation removes the vacancy by accepting the current count, but pending
members remain pending. The success message reports remaining confirmations or
other attention reasons rather than implying the team is ready. Refreshing the
roster clears old action feedback and reloads the authoritative state. These
changes use the existing roster API and reason strings, without a migration or
new approval policy.

A successful save remains successful if the follow-up event-details read fails.
The updated roster and card success message stay visible alongside a separate
“Change saved” warning that asks the organizer to refresh the page. The write is
already committed; a failed read does not require resubmitting it. Save requests
with a lost response still retain their request ID for a safe retry.

Browser regressions cover replacement and approval with a failed follow-up read
against the real API and database. Focused response fixtures cover approval with
overdue confirmations, fully confirmed teams becoming ready, disabled styling,
and retrying an unknown save outcome with the same request ID and version.

Moves/swaps use active members from the same event and validate both resulting
team sizes before changing anything. A valid move/swap explicitly approves those
new sizes and resets confirmations in both teams. Reassignment after the deadline
requires an extension first. No organizer action bypasses the hard size limits.

## API and privacy

| Method | Path suffix under `/events/{id}`   | Access                                                                   |
| ------ | ---------------------------------- | ------------------------------------------------------------------------ |
| POST   | `/grouping-runs/{run_id}/finalize` | Owner; `{version}`                                                       |
| GET    | `/teams`                           | Owner gets all teams; registered participants get only their active team |
| POST   | `/teams/{team_id}/confirm`         | Assigned participant; `{decision, team_version}`                         |
| POST   | `/teams/withdraw`                  | Participant's own registration/assignment                                |
| POST   | `/teams/{team_id}/replace`         | Owner; version/request ID                                                |
| POST   | `/teams/{team_id}/continue`        | Owner; version/request ID                                                |
| POST   | `/teams/reassign`                  | Owner; version/request ID and participant/target/optional swap IDs       |
| POST   | `/teams/deadline`                  | Owner; version/request ID and new deadline                               |
| GET    | `/teams/export`                    | Owner only                                                               |

The existing DELETE registration route delegates to the same finalized-withdrawal
service. Authenticated writes use the existing origin and CSRF checks. All team
responses are `no-store`. Participants cannot see unrelated teams, retired
teammates, or emails through these endpoints. CSV text fields are quoted and
formula-prefixed values are escaped for spreadsheet safety.

Completed history uses actual active finalized assignments, excluding withdrawn
or declined members. Legacy completed runs without separate final rosters still
derive history from their stored team memberships. A final roster suppresses that
legacy fallback for its event, preventing proposal and assignment double counting.
Event completion APIs are not added in this slice; historical fixtures remain
trusted test/demo data until that lifecycle action is implemented.

## Verification and recovery

Local verification passed: 91 backend tests, eight live-browser tests, migration
and schema comparison, Python/web formatting, lint, type checks, and the production
frontend build. Hosted CI and deployment have not been verified.

Tests cover finalization freshness/integrity, retry and competing finalizations,
member-only visibility, deadlines, decline/withdrawal, FIFO promotion, concurrent
replacement, stale confirmations, reassignments, valid/invalid continuation,
rollback, cancellation, database uniqueness, actual-roster history, and CSV
privacy/formula handling. The browser flow exercises finalization through
confirmation, decline, replacement, swap/reconfirmation, extension, export, and
an unfillable vacancy.

The migration adds tables, optional audit fields, and a composite uniqueness
constraint. Existing previews and registrations remain intact. Downgrade refuses
to discard any populated final roster; back up and resolve assignments through a
separate explicit recovery decision before rolling this phase back.
