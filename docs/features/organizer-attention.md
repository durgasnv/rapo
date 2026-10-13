# Organizer attention overview

**Manage events** now includes **Events needing attention** above the existing
event list. The panel shows short reasons and a **Manage event** link for each
affected event. It refreshes on demand and paginates 20 events at a time.

## What appears

- Proposed groupings: **Preview awaiting review**. Review may require regeneration
  if inputs changed or the finalization deadline passed; the summary does not
  promise the proposal can still be finalized.
- Published events with a recorded `FAILED` or `BLOCKED` grouping job: **Grouping
  failed** or **Grouping blocked**. Open the event for job details and current
  available actions. A recorded failure can remain visible after its cutoff;
  this panel does not promise that retrying is still allowed.
- Finalized events with roster issues: **Below minimum** or **Above maximum**
  counts affected teams, **Vacancy** counts unfilled target places, and
  **Confirmation overdue** counts pending members at or after the deadline.

Pending and confirmed members count as active, matching the final roster.
Withdrawn and declined members do not. Empty teams still contribute minimum-size
and vacancy counts. Pending members before their deadline do not need attention
by themselves. Several reasons can apply to one event.

An event with a proposal shows the review reason instead of an older job failure.
After finalization, only current roster issues apply. Draft, in-progress,
completed, and cancelled events are excluded. Fixing the last issue removes the
event on refresh or the next visit. Due jobs without a recorded failure and
completion reminders are outside this slice.

## UI → API → database

`organizer-events.tsx` renders `organizer-attention.tsx` only for signed-in
organizers, keyed by account ID so changing accounts resets private panel state.
The panel calls `GET /organizer/attention?offset=0&limit=20` through the existing
cookie-authenticated API helper. Loading, empty, failed-read, refresh, and
pagination states are independent of the original event list. A failed attention
read does not prevent managing events through that list.

The events router checks organizer access, validates offset and limit, sets
`Cache-Control: no-store`, and delegates to `services/attention.py`. The service
filters by the authenticated organizer ID; no client-supplied owner ID is accepted.
Its response contains event ID, title, start time, timezone, lifecycle status,
and reason strings. It contains no member identities, emails, history, or raw job
diagnostics.

PostgreSQL aggregates active/pending assignments per final team, retaining empty
teams through an outer join, then aggregates issues per event. The service joins
those counts and grouping job status to owned events. Filtering happens before
pagination, with stable start-time/ID ordering. It runs two data queries, for total
and page, plus existing authentication reads; query count does not grow per event.
The attention list is not restricted by the original event list's 100-event cap.

This is read-only: it does not create teams, repair assignments, change deadlines,
retry jobs, or add audit/notification records. There is no migration or dependency
change. The existing management APIs remain responsible for mutation validation.

## Recovery and limits

Use **Refresh attention** after repairs; this returns to the first page. Counts
and pages can change as other requests or the worker update events. An empty page
explains how to refresh. Opening an event reloads its current authoritative state.
This is a current summary, not a frozen snapshot or live subscription.

The existing general event list still has its previous 100-event limit. The new
attention panel independently reaches all affected owned events. The number of
queries is bounded, but database work still grows with the owner's roster data;
this is not a measured latency guarantee at arbitrary scale.

## Alignment and bug review

The feature supports existing organizer preview, confirmation, and withdrawal
workflows (FR-09, FR-11, FR-12). It preserves organizer ownership, final roster
membership rules, hard size limits, confirmation deadlines, and explicit manual
remediation. SQL aggregation is needed to filter and paginate summaries without
loading each private roster separately; boundary tests compare it with roster
behavior. No new product policy or unrelated feature was introduced.

The final review checks bugs, unnecessary changes, missing tests, security, and
breaking changes as required by the updated `docs/AGENTS.md`. Review identified
that disabled pagination buttons inherited the global wait cursor. Scoped panel
styles now make disabled controls muted with a normal cursor, with browser
coverage. Tests also protect against empty-team omission, retired-member counting,
old failure messages overriding current state, ownership leakage, and pagination
truncation. Remaining operational limits are stated above.

## Verification

Integration tests cover authentication/role checks, cross-owner exclusion,
response privacy, read-only behavior, pagination validation and more than 100
affected events, constant query count, preview/job state precedence, terminal
states, roster counts, empty teams, resolved vacancies, and the deadline boundary.
Browser tests cover error recovery without blocking the event list, pagination
and refresh, disabled-control styling, real preview review navigation, real
vacancy repair clearing the summary, and completed-event exclusion.

Local verification (2026-10-13): all 139 backend tests passed. The nine focused
attention tests passed again after adding explicit declined-member coverage. Both
browser flows passed; the attention pagination/recovery flow passed again with
its final disabled-style assertions. Python and frontend lint, formatting, type
checks, and the production build passed. Tests used an isolated PostgreSQL
database and separate browser-server ports.

No remaining feature issues were found in the final alignment, bug, privacy,
and compatibility review. This is local verification; hosted deployment remains
unverified. The manual-refresh and existing general-list limits remain as stated
above.
