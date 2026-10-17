# Event dashboard

After signing up or signing in, participants land on `/dashboard` and immediately
see the community's available events. The existing greeting remains, followed by
the event cards, notifications, and their registrations. Organizers retain their
management link. The signed-in navigation labels this destination **Dashboard**.

The public `/events` page and dashboard share `EventList`. Both load automatically
without requiring filter input. A compact toolbar above the cards provides:

- **Filter:** optional UTC start-date bounds and event status, with an applied
  filter count. The form opens on demand and provides Apply and Clear actions.
- **Sort:** soonest start first (default), latest start first, or case-insensitive
  event name A–Z. Changing the selection immediately reloads the first page.

Applying or clearing filters also resets pagination. Clearing filters preserves
the selected sort. Invalid date ranges leave the currently displayed results
intact and show an error inside the open filter form. Empty results and API
failures have distinct messages; failed requests can be retried. Native details,
summary, labels, buttons, and selects support keyboard interaction. The filter
panel's width and position keep it within small viewports.

## Request and database flow

`AuthForm` already routes successful sign-up and sign-in to `/dashboard`; the
change replaces the dashboard's extra discovery link with the event listing.
After the account check, `EventList` calls the existing `/events` API through
`apiRequest`. Requests include `limit`, `offset`, `sort`, and any applied
`date_from`, `date_to`, or `status` filters. Stale responses are ignored when
selections change or the component unmounts.

The API validates `sort` against `soonest`, `latest`, and `title`, and uses fixed
SQLAlchemy ordering expressions. It filters and sorts in PostgreSQL before
offset/limit, with event ID as a deterministic tie-breaker. This orders the full
catalog rather than only the visible page. Default ordering and the response
shape remain compatible with existing callers. No migration or dependency is
required.

The listing retains the existing public statuses: `PUBLISHED`, `GROUPS_PROPOSED`,
and `GROUPS_FINALIZED`. Draft, cancelled, and other private events cannot be
exposed through a filter or sort. Registration windows, organizer permissions,
team formation, and participant data access retain their existing rules.

## Review and verification

The implementation review checked shared-component reuse, pagination resets,
request races, default compatibility, keyboard controls, mobile bounds, and
private-event visibility. Review also found that the old inclusive date filter
overflowed when adding a day to `9999-12-31`. Comparing against the selected day's
last microsecond preserves inclusive UTC filtering without that overflow.

All 16 event API tests passed against a disposable local PostgreSQL database.
They cover stable ordering across pages, name case, combined date/status filters,
maximum dates, invalid sorts, and existing event permissions and lifecycle rules.
The browser tests use real sign-up and session APIs with a controlled event
catalog so parallel tests' published events cannot change their expectations.
The real catalog query behavior is covered separately by PostgreSQL API tests.
Browser coverage includes automatic discovery after sign-up, paging and sort
query parameters, date validation, empty results, clearing filters, status
filters, retry, and keyboard/mobile controls.

The production build, frontend lint, scoped browser-test TypeScript checks,
Python lint/formatting/type checks, and whitespace review passed. All seven
scoped browser checks passed across the main run and a focused retry-test rerun
after correcting test selectors. Existing sign-in/session, organizer event
management, and health/retry journeys also passed. Desktop and mobile screenshots
were inspected, and the mobile filter panel's horizontal bounds were asserted.
No remaining alignment, security, or compatibility issues were found within this
change's scope. Test data stayed in a disposable local database.

Filter and sort selections are local to the mounted listing. Reloading the page
restores the default catalog and soonest-first ordering.
