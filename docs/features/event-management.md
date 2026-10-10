# Event management and discovery

## User experience

Visitors can browse published events, filter by UTC start date, paginate results,
and open an event's details. Authorized organizers can create drafts, edit them,
review schedules, publish, and cancel owned events. Their management screen
shows up to the latest 100 owned events. Participants cannot manage events.

The form currently asks for schedule times in UTC. A separate IANA timezone
controls how event details and the schedule preview are displayed. This keeps
stored instants explicit and avoids guessing how local clock times map across
daylight-saving transitions. Local-time entry in a selected timezone is a future
UI improvement. The API accepts timestamps with an explicit offset and rejects
naive timestamps.

## Validation and lifecycle

The API enforces:

- Registration opens before it closes, registration closes no later than event
  start, and event end follows start.
- Minimum/maximum team sizes are positive and ordered. Fixed sizes use equal
  bounds. Capacity can be absent; otherwise it must fit at least one team.
- Grouping defaults to the later of registration close or three days before
  event start. An explicit grouping time must respect the same date constraints.
- Confirmation cannot precede grouping or follow event start. Publication requires
  registration to close in the future.
- Only `DRAFT → PUBLISHED`, `DRAFT → CANCELLED`, and `PUBLISHED → CANCELLED`
  are currently implemented. Published fields are read-only in this slice.

The saved draft displays its computed schedule before the organizer publishes it.
No grouping job runs yet; this phase stores the configuration only. Phase 2 adds
[registration and waitlists](event-registration.md). Later phases add automated
transitions and team formation.

## Ownership, transactions, and stale forms

The server sets `organizer_id` from the authenticated account; requests cannot
choose it or set status directly. An organizer cannot read another organizer's
private event. Private/unknown identifiers return 404. Public lists and detail
routes expose published events only, even if a caller supplies a draft status.

Each edit, publish, or cancel request supplies the current version. The server
locks the event row, checks ownership and version, validates the transition,
increments the version, and writes an audit action in one transaction. A stale
form gets 409 with instructions to refresh. For a partial edit, changing event
start or registration close recomputes the default grouping time unless an
explicit grouping time is supplied. The frontend submits the full form, including
the displayed grouping time, so its schedule is validated as shown.

API routes live in `app/routers/events.py`, validation in
`app/schemas/events.py`, and SQLAlchemy entities in `app/models.py`. The frontend
keeps forms and lists separate from the account/session provider and API client.

## Verification and remaining work

PostgreSQL API tests cover full draft/edit/publish/cancel behavior, audit records,
private drafts, participant denial, cross-owner denial, stale writes, malformed
dates/timezones, invalid capacity/sizes, and public pagination/filtering. Browser
tests exercise the organizer flow and verify anonymous draft/public/cancelled
visibility against the live API.

The current audit records capture actor, event, action, and time; richer before/
after snapshots and an audit UI remain future work. Notifications, finalized
teams, and later event lifecycle states are not available
yet. Registration and waitlists are implemented in Phase 2, with a private roster
on the event management page. Cancellation preserves event, registration, and
audit history; participant dashboards explicitly display the cancelled event.
Registration changes increment the event version, so reload an outdated event
management page before attempting cancellation.
