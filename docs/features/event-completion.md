# Event completion and collaboration history

Organizers can mark an owned event completed from **Manage event** using **Mark
event completed**. Completion is available for finalized events after their end
time; the API rejects an early attempt and displays a readable error. An event
in the existing `IN_PROGRESS` state can also complete, although this slice does
not introduce a separate start-event action.

The UI explains the existing history policy before completion: pending and
confirmed final members count, declined and withdrawn members do not. This is
assignment history, not verified attendance. There is no attendance collection,
automatic confirmation, or automatic removal of pending members in this slice.
Completion preserves unresolved roster reasons instead of marking every team ready.

## Request and transaction

The browser posts `{ "version": <current event version> }` to
`POST /events/{id}/complete`, with the existing session cookie and CSRF header.
The thin events router delegates to `services/event_completion.py`.

The service locks the event row using the shared organizer ownership helper.
This is the same lock used by roster mutations, so competing changes serialize.
It checks ownership, version, lifecycle state, end time, and the presence of a
final roster belonging to a finalized grouping run. It changes the status to
`COMPLETED`, increments the version, and records `event.completed` with before
and after status/version. The existing database dependency commits the status
and audit record together or rolls both back on failure.

An already-completed event returns its current result, including when a retry
supplies the previous version after losing the first response. This creates no
second audit record or version increment. Other stale requests return 409. A
participant receives 403, another organizer receives 404, and an unauthenticated
request receives 401. Existing CSRF protection also applies.

## How history affects the next event

The grouping service already derives pair frequencies from completed events.
For example, if Alice and Bob remain in the same final team when their event is
completed, their pair frequency increases by one for future eligible grouping.
If Bob withdrew or declined, that pairing does not count. Pending memberships
still count under the existing policy. Each completed event contributes at most
one count per pair.

No counter is incremented during completion. Future grouping reads retained
final assignments, so retrying completion cannot double-count collaboration.
Replacements and moves are reflected by the actual final roster, rather than
its original proposal. Legacy completed runs without a separate final roster
continue using their stored proposal memberships.

Completion can make an existing future-event proposal stale because its history
input changed. Finalization rejects that stale proposal; the organizer generates
a new preview using the updated history. Scores remain heuristic, not guaranteed
global optima.

## Viewing and recovery

Completed events remain in the organizer's event list and participant dashboard.
Their public event details remain reachable by existing links, while team names
and membership remain restricted by the existing owner/member authorization.
Completed events are excluded from the active public discovery list. The final
roster and organizer CSV export remain available, with mutation controls closed.

There is no reopen/undo endpoint. Review the displayed membership policy before
completion. A failed request leaves the previous state intact; if its outcome is
unknown, retrying is safe. Refreshing the page also reloads authoritative status.
No database migration or new dependency is needed: the completed status, roster,
and audit fields already exist.

## Verification

Integration tests cover completion timing including the exact end boundary,
allowed and rejected lifecycle states, ownership/role/CSRF checks, stale versions,
missing final rosters, response-loss retries, atomic rollback, and concurrent
completion. A history test includes pending and confirmed members, excludes
withdrawn and declined members, checks each pair is counted once, and verifies
that an existing proposal becomes stale and its replacement includes history.

The browser lifecycle exercises early rejection, organizer completion after end,
the persisted event response, closed roster controls, and participant navigation
from the dashboard to the completed team. Existing feedback tests guard against
regressions in approval and replacement messages.

Local verification (2026-10-12): all 130 backend tests passed, and the 10
completion tests passed again after strengthening the history fixture. The real
lifecycle browser test and three focused roster-feedback browser tests passed.
Python/frontend lint, formatting, type checks, and the production build passed.
Verification used an isolated PostgreSQL database and separate browser-server
ports; hosted deployment remains unverified.
