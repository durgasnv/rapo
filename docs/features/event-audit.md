# Owner-only event activity

**Manage event → Event activity** shows who performed recorded actions and when.
Entries are newest first, with 20 per page and **Newer activity**, **Older
activity**, and **Refresh activity** controls. The timeline remains available
for drafts, active events, cancelled events, and completed events.

## What is displayed

The API translates stored action codes into readable descriptions for event
creation/editing/publication/cancellation/completion, manual and scheduled
previews, finalization, confirmation/decline/withdrawal, waitlist replacement,
current-size approval, deadline extension, reassignment, and registration changes.

Each entry contains its record ID, known action code, description, actor name,
and timestamp. The UI displays description, actor name, and the time in the
event's timezone. Names are read from current profiles; renaming a profile changes
labels on its older actions. Actor emails and global profile IDs are omitted.

The worker records scheduled grouping using the organizer's actor ID for event
ownership context. Its public actor label is **Scheduled worker**, so the timeline
does not attribute an automatic action to a person. Demo setup actions similarly
use **Demo setup**. Unknown future action types remain visible as **Other event
activity**, with an `other` code; the unknown internal string is not exposed.

Before/after snapshots remain stored for internal auditing. They can contain
member IDs and other private data, so this view returns no raw JSON or membership
diff. This slice reads existing records without changing their creation logic.

## UI → API → database

`organizer-editor.tsx` renders `event-audit.tsx` after loading an owned event. Its
key includes event ID, account ID, and event version. A successful event transition
or refreshed roster change therefore resets the activity panel to the newest
page and reloads it. Different events/accounts cannot reuse private panel state.
External changes and successful writes whose parent-details refresh failed can
be loaded using **Refresh activity**. There is no polling or live subscription.

The panel calls `GET /organizer/events/{event_id}/audit?offset=0&limit=20` using the
existing authenticated API helper. Loading, empty, and failed-read states are
independent of event mutation controls. A failed audit read does not prevent
publishing or managing the event.

The events router enforces the organizer role and validates nonnegative offset
and a limit of 1–100. `services/audit.py` verifies event ownership using the
existing shared row-lock helper before reading records. The shared lock uses
the same event row as the write paths, so count and page are read while event
mutations wait for this short request to finish. The service selects only record
ID, action, timestamp, and actor name through a join; snapshots and emails are
not fetched. Ordering uses creation time descending and ID descending for ties.
Actor lookup is joined, preventing a query per displayed entry.

Unauthenticated callers receive 401, participants receive 403, and another
organizer or a missing event receives 404. The existing private-route middleware
sets `Cache-Control: no-store`, including failed responses. The API accepts no
client-supplied actor or owner ID. It exposes only GET and does not add audit
records, modify versions, or affect assignments and history.

## Recovery and limits

Refreshing returns to the newest page. An empty older page explains how to return.
New actions between separate page requests can shift offset pagination; each
page reflects current committed data rather than a frozen browsing snapshot.

This view presents the records that exist. Older events with no records show an
empty state. New action writers should extend the description mapping; unfamiliar
codes use the safe fallback until then. No edit/delete controls, actor-name
snapshots, raw change inspector, export, or new notification behavior are added.
No database migration or dependency is required.

## Alignment and bug review

The feature fulfills the audit-view milestone and supports FR-16 auditability.
It preserves the modular monolith, thin routers, existing transaction/audit
writers, organizer ownership, privacy boundaries, and all lifecycle mutation
rules. Completed/cancelled history remains readable without reopening events.

The review identified two risks and addressed them: scheduled actions would be
misattributed to the organizer without a system label, and unfamiliar action
strings could expose internal details if returned verbatim. Explicit system
labels and a safe fallback prevent both, with integration coverage. Pagination
controls reuse the scoped disabled styling introduced for organizer attention,
so unavailable pages use a normal cursor. Existing browser response fixtures
were updated to support the additional independent audit read.

## Verification

Integration coverage includes roles/ownership and missing events, response
privacy, unknown actions, worker/demo attribution, current actor names, stable
ordering at tied timestamps, pagination bounds and empty pages, joined actor
query count, read-only behavior, and retained logs across lifecycle states.

The browser checks failed-read recovery, pagination, disabled controls, timestamps,
empty state, and automatic first-page refresh after publication. The real team
lifecycle verifies finalization, a saved replacement even when the parent refresh
fails, reassignment, deadline extension, size approval, and completion in the
activity view. Existing roster feedback regressions also run with the new panel.

Local verification (2026-10-14): all 151 backend tests and five targeted browser
tests passed, including the real team lifecycle. Python/frontend lint,
formatting, type checks, and the production build passed. Verification used an
isolated PostgreSQL database and separate browser-server ports. Hosted deployment
remains unverified.

The final scope, alignment, bug, privacy, and compatibility review found no
remaining issues within this feature. Current-name labels and changing offset
pages remain the documented limits; existing mutation and audit-writing behavior
is preserved.
