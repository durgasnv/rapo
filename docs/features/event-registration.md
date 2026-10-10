# Registration and FIFO waitlists

## User experience

Signed-in users can register from a published event's detail page during its
registration window. A free seat gives `REGISTERED`; a full fixed-capacity event
gives `WAITLISTED` with a current, one-based queue position. Events without a fixed
capacity always register the user. All account roles may participate; no extra
event-specific eligibility requirements are configured in this release.

The event page shows registered/waitlisted counts and the user's own status. The
account dashboard lists their events, including withdrawals and cancelled events.
The organizer's existing management page contains a private, paginated roster of
names, statuses, and join times. Participant emails are not included in it, and
participants cannot see the roster or someone else's registration.

Use **Refresh registration**, **Refresh registrations**, or **Refresh roster** to
see changes made by others. Promotions do not yet send notifications or push live
updates. Buttons reflect the last server response; the server rechecks deadlines
and capacity when an action arrives.

## Windows, withdrawal, and retries

- A new join is allowed at registration opening, up to but excluding closing.
- Withdrawal and automatic promotion are allowed strictly before `grouping_at`
  while the event is published. This also permits promotion after registration
  closes, if grouping is later. No new joins are allowed after closing.
- Withdrawing a registered participant promotes the oldest remaining waitlisted
  participant in the same transaction. Withdrawing from the waitlist frees no
  seat; remaining positions simply compact.
- Repeating an active join returns its existing registration without moving it in
  the queue, even if registration has since closed. Repeating a completed
  withdrawal is a no-op. A retry after a successful promotion cannot promote a
  second person accidentally.
- Rejoining while registration is open reuses the unique user/event row, updates
  its join time, and assigns a new ticket behind everyone already waiting.
- A cancelled event accepts no joins, withdrawals, or promotions. Its existing
  registration records remain as history. The dashboard displays **Event
  cancelled**, overriding the stored pre-cancellation registration status.

Freezing self-service changes at the scheduled grouping time is this phase's
boundary. There is no grouping worker yet. Phase 4 will add withdrawal and
replacement rules around real proposals and finalized teams. The event still has
status `PUBLISHED` after registration closes; the timestamps enforce the window
without a scheduler changing its status.

## API and request flow

| Method | Endpoint                     | Access                | Result                                                                 |
| ------ | ---------------------------- | --------------------- | ---------------------------------------------------------------------- |
| GET    | `/events/{id}/registration`  | Signed-in user        | Own status, counts, capacity, and open/closed flags                    |
| POST   | `/events/{id}/register`      | Signed-in user + CSRF | Register, waitlist, or return existing active registration             |
| DELETE | `/events/{id}/registration`  | Signed-in user + CSRF | Withdraw and promote atomically, or return an already-withdrawn result |
| GET    | `/me/registrations`          | Signed-in user        | Paginated own registrations with event information                     |
| GET    | `/events/{id}/registrations` | Owning organizer      | Paginated roster and registered/waitlisted counts                      |

Lists default to 20 rows and accept `offset >= 0` and `1 <= limit <= 100`.
The roster groups registered users, waitlisted users in FIFO order, then withdrawn
users. The dashboard orders by latest join time. Private responses, including
authorization errors, use `Cache-Control: no-store`.

`EventRegistration` calls the typed browser API client, including the session
cookie and CSRF header. The registration router obtains the authenticated user;
it never accepts a target user, role, or registration status from the browser.
The service locks the event, validates its current state/time, checks capacity,
and changes the registration. The request's database dependency commits before
the response is sent or rolls back on an exception. The browser then displays
the server's returned status rather than predicting whether it won the last seat.

## Storage and concurrency

The `c72a0e51b238` Alembic migration creates `registrations`, with foreign keys to
users/events, a unique `(event_id, user_id)`, valid-status and positive-ticket
checks, and indexes for user lookups and event/status/queue queries.

Each accepted join gets `queue_number = maximum ticket for this event + 1` while
holding the event row's `FOR UPDATE` lock. Tickets are unique within each event;
FIFO therefore does not depend on clock precision or UUID ordering. We calculate
the displayed position from active waitlisted tickets instead of rewriting every
row whenever someone leaves. Cancelled rows are retained, so ticket allocation
continues increasing and a rejoin cannot recover its old priority.

All joins, withdrawals, promotions, and event cancellation serialize on the same
event row. A second last-seat request waits for the first transaction, then counts
its committed seat and joins the waitlist. Withdrawal and promotion are one
transaction: a new join cannot observe the vacancy between them or jump ahead of
the queue. Deadlines are checked after acquiring the lock. Read-only status and
roster requests use a shared event lock to keep their counts/positions consistent
with registration updates. Dashboard rows and positions share one SQL statement
snapshot; its separate pagination total may change during concurrent activity.

Effective joins and withdrawals increment the existing event version. An organizer
whose event changed underneath an open form must reload before cancelling it.
Join/withdraw audit records capture actor, event, action, and time; detailed
before/after snapshots and a promotion notification remain future work.

The capacity invariant is enforced by the service's event-lock protocol, not by a
cross-row database check. Any future worker or administrative registration writer
must use the same lock. Locks are per event, so unrelated events can change in
parallel. This simple approach suits the MVP; throughput has not been benchmarked.

## Failure and recovery

A private/unknown event returns 404; missing authentication returns 401; incorrect
CSRF/origin or participant roster access returns 403. Closed windows and changes
outside the supported withdrawal period return actionable 409 errors. Failed
transactions leave the original registration and waitlist intact. After a network
timeout, refresh to inspect the committed state; retrying the same join or
withdrawal is safe. A later intentional rejoin is a new participation attempt.

There are no hard deletes for registration withdrawal or event cancellation.
Account deletion/retention policy remains an MVP follow-up; these new foreign keys
preserve referenced records. Registration histories expose only the user's own
events or the owning organizer's roster.

## Verification

PostgreSQL tests cover capacity and uncapped events, FIFO and rejoining, duplicate
requests, opening/closing/grouping boundaries, promotion after cutoff, event
cancellation, database constraints, pagination, authorization, CSRF/CORS, caching,
and rollback after a failed withdrawal. Concurrent HTTP requests use separate
database sessions and committed fixtures in an isolated test schema, exercising
the last seat, duplicate joins, duplicate withdrawals, competing waitlist
withdrawals, and a new join racing with promotion.

Browser tests cover capacity/waitlist/withdrawal/promotion, session refresh,
dashboard status, the private organizer roster, unlimited registration, and
cancelled-event visibility. Existing account/event browser tests also run.

To try it manually, publish an event with minimum team size 1 and capacity 1,
with registration currently open and grouping in the future. Sign in as two
participants in separate browser profiles. Register both, withdraw the first,
then refresh the second's registration: it should change from **Waitlisted ·
position 1** to **Registered**.

Learning check: why would counting available seats without first locking the
event allow two simultaneous requests to claim the last seat?
