# Scheduled grouping and private notifications

This is the automation slice of Phase 5. A separate worker creates a preview when
an event's grouping time arrives. The owner must still review and finalize it.
Each account has a private, paginated notification inbox on **My account**, with
an unread filter, refresh, and retry-safe **Mark as read**. Organizer event pages
show scheduled grouping status, attempts, failures, and the next retry time.

Hosting, public deployment, email, event completion, and automatic deadline
removal are outside this slice. No new dependencies or external message service
are required. The HTTP server does not start a hidden scheduler.

## Run locally

Apply migrations before starting the API and worker:

```bash
uv run --env-file apps/api/.env alembic upgrade head
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.jobs.grouping --once
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.jobs.grouping
```

Use `--once` for a bounded batch, such as a host's scheduled command. Without it,
the worker checks every 30 seconds. `--interval` accepts 1–3600 seconds and
`--batch-size` accepts 1–1000 events (default 100). Run a supervised worker process
in deployment; restarting it is safe. SIGINT/SIGTERM stop after current work.
The worker needs the same database URL as the API, including the applied schema.

The scheduled time is the existing validated event `grouping_at`: by default,
three days before start, or registration close if that is later. The worker
requires a published event, closed registration, reached grouping time, and an
open confirmation window before event start. It skips draft, cancelled,
finalized, started, expired, and already-proposed events. A missed cutoff is
shown as `EXPIRED`; a late worker does not create an unusable preview.

Refresh **Scheduled grouping** and **Grouping preview** to see a new proposal.
Screens do not poll. Finalize before the deadline, then participants receive
assignment notices and can review their own team.

## Worker transactions, retries, and failure policy

`apps/api/app/jobs/grouping.py` scans eligible events in schedule/ID order.
Each event has its own transaction. PostgreSQL `FOR UPDATE OF events SKIP LOCKED`
claims the event while other workers continue with unlocked events. The worker
uses the same event lock and grouping service as manual grouping, registrations,
finalization, and cancellation. A deterministic event-specific request UUID and
seed make scheduled creation reproducible and retry-safe.

`GroupingJob` has one row per event, its result, attempt count, safe code/message,
next retry time, update time, and optional resulting run. A composite foreign key
keeps that run in the same event. Successful jobs require a run; failed/blocked
jobs cannot reference a partial run.

A savepoint encloses generation, proposal rows, notification, and scheduled audit.
An unexpected error rolls those writes back and records `FAILED`, with retries
starting after 60 seconds and doubling to a maximum of one hour. Only exception
class and event ID are logged, never raw exception text or participant details.
Database/connection failures that prevent recording the attempt leave it eligible
for a later worker poll. `--once` exits nonzero for processing or database errors.

Known feasibility failures (too few people, unpartitionable counts, or the engine's
100-person limit) record `BLOCKED`, an actionable reason, and an owner notification.
They retry after five minutes while the event remains eligible. Identical blocked
reasons notify once per event/code. This avoids flooding an owner every poll.
The owner may inspect registrations, generate manually if inputs become feasible,
or cancel. Published-event editing is still limited by earlier phases.

An existing manual preview is preserved even if stale; automatic retries do not
replace a proposal awaiting review. A deliberate manual generation that follows a
scheduled run may create another preview, as before. This differs from duplicate
scheduled processing: one scheduled run is saved at most once. After a successful
scheduled run, later withdrawals/history changes require manual review/regeneration.

Process death releases the database lock and rolls back uncommitted work. A crash
after commit leaves the proposal/job/notice together; another poll skips it. No
persisted `RUNNING` state requires a stale lease to be cleared.

The scheduled audit action is `grouping.scheduled`. Its actor and the run's
`created_by` identify the event owner on whose behalf automation runs; this action
explicitly distinguishes it from an owner's manual trigger.

## Notification production and privacy

`services/notifications.py` writes inbox rows inside the original transaction.
A uniqueness constraint on `(user_id, dedup_key)` and PostgreSQL conflict handling
make repeated delivery safe. A failed inbox write rolls back the associated
change, so the UI cannot show an assignment notification for an unsaved assignment.
There is no external delivery step or background notification queue.

| Change                                       | Recipients                                                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------ |
| Scheduled proposal ready or blocked          | Event owner                                                                    |
| Finalized assignment or waitlist replacement | Newly assigned participant; owner receives roster update                       |
| Withdrawal, decline, move, swap, replacement | Affected active teammates get reconfirmation notices; owner gets roster update |
| Confirmation                                 | Event owner                                                                    |
| Deadline extension                           | Active assigned participants and owner                                         |
| Valid continuation approval                  | Event owner                                                                    |
| Assignment retired                           | Retiring participant                                                           |
| Pre-finalization FIFO promotion              | Promoted participant                                                           |
| Event cancellation                           | Currently registered and waitlisted participants                               |

Messages contain an event title and generic status text. They contain no emails,
passwords, session tokens, collaboration history, or other participants' names.
Recipient ownership is checked on every read/update. Responses are `no-store`;
mark-read requires the existing session, allowed origin, and CSRF token.
Read retries preserve the original read timestamp.

Cancellation and retired-assignment notices link to the account dashboard because
cancelled events are not public. Other notices link to the event or organizer
screen according to their recipient. Old event notices can describe an earlier
state; the destination's current state remains authoritative. Inbox rows are kept
until an explicit retention/deletion policy is implemented; this slice performs
no automatic deletion or backfill for earlier changes.

## API and files

| Method | Path                                                    | Access                                |
| ------ | ------------------------------------------------------- | ------------------------------------- |
| GET    | `/events/{id}/grouping-job`                             | Event owner only                      |
| GET    | `/me/notifications?offset=0&limit=20&unread_only=false` | Current account only; limit up to 100 |
| POST   | `/me/notifications/{notification_id}/read`              | Recipient only, with CSRF             |

The routers delegate to services. Lifecycle hooks connect finalization/roster
changes, registration promotion, and cancellation to notification delivery.
New persistence lives in `models.py` and the Phase 5 Alembic migration. UI lives
in `notifications.tsx`, `grouping-schedule.tsx`, the account dashboard, and the
organizer editor.

## Verification and recovery

Local verification passed: 112 backend tests (21 automation/notification cases),
nine live-browser tests, the worker CLI smoke check, migration/schema comparison,
Python/web formatting, lint, types, and the production frontend build. Hosted CI
and deployment have not been verified.

Backend tests exercise due-time eligibility, retries/backoff, infeasible recovery,
rollback after partial generation and notification failure, simulated process
crash, concurrent workers/manual generation, private reads, CSRF, pagination,
mark-read retries, recipient selection, and deduplication. Browser tests exercise
scheduled generation through explicit approval, inbox filtering/read persistence,
withdrawal, reconfirmation notices, and cancellation notifications.

Check a failing worker's safe JSON logs and the owner's scheduled status. Restore
database connectivity or fix the cause, then rerun a batch. Do not delete job
records to retry a successful job; use the owner's manual preview action instead.
Stop all workers before rolling back application code/schema. The migration is
additive and preserves existing registrations, teams, and audits. Downgrade
refuses to discard any job or inbox records; back up and explicitly resolve those
records first. Hosted scheduling and deployment need separate verification.
