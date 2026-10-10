# Grouping previews

Phase 3 lets an event owner generate, reload, and review proposed teams after
registration closes and before the event starts. Proposals do not finalize
assignments or notify participants automatically. Phase 4 adds explicit
[finalization, confirmations, and replacements](team-lifecycle.md); scheduled
processing remains Phase 5.

## Try it

1. Apply migrations with `uv run --env-file apps/api/.env alembic upgrade head`.
2. Sign in as the event owner and open the organizer's event management page.
3. After registration closes, choose a seed and select **Generate team preview**.
4. Review team membership, weighted repeat score, random baseline, fairness
   penalty, and per-team explanations. Reloading restores the latest proposal.
5. Select **Refresh preview** to check whether its inputs changed. Regenerate a
   stale proposal; a failed regeneration leaves the previous proposal visible.

The seed reproduces an assignment only with the same participant IDs, pair-history
snapshot, size limits, and algorithm version. Changing the seed explores a new
starting point; it does not promise an improved assignment.

## Request flow and persistence

`GroupingPreview` calls owner-only FastAPI routes. The router validates the request
and delegates to the grouping service. The service locks the event, reads active
`REGISTERED` users and completed history, invokes the pure Python engine, and
saves a `GroupingRun`, its `Team` rows, and `TeamMember` rows in one transaction.
The event becomes `GROUPS_PROPOSED`, its version increments, and an audit entry is
written. Events with previews stay publicly discoverable; their private teams do
not appear in public event responses.

Endpoints:

| Method | Path                                  | Behavior                                             |
| ------ | ------------------------------------- | ---------------------------------------------------- |
| POST   | `/events/{id}/grouping-runs`          | Generate with `{request_id: UUID, seed: integer}`    |
| GET    | `/events/{id}/grouping-runs/latest`   | Latest preview, or `null` if none                    |
| GET    | `/events/{id}/grouping-runs/{run_id}` | Read one stored preview and its current stale status |

Writes require the existing session, organizer role, ownership, allowed origin,
and CSRF token. Reads require role and ownership. Responses are `no-store`.
Feasibility failures return HTTP 422 with `detail.code` and `detail.message`;
event/time conflicts return 409. No failed generation changes the event or leaves
partial team rows.

Request IDs are unique within an event. Concurrent retries with the same ID and
seed return the same stored proposal without duplicate teams or audit entries.
Reusing an ID with a different seed returns 409. The browser retains its ID after
a network failure because the server may have committed before the response was
lost. A deliberate new generation uses a new ID and may create a separate proposal
even with the same seed.

## Collaboration history

History uses active final assignments for `COMPLETED` events whose grouping run
is `FINALIZED`. For legacy completed events without a separate final roster, it
uses the approved proposal memberships. Events must have ended before both the
current time and the target event's start.
Each unordered pair counts once per completed event. Cancelled events, proposed
runs, current-event proposals, and events that have not ended never count.
An event can have at most one finalized run, enforced by a partial unique index.

The service stores relevant pair frequencies and original size limits as a private immutable snapshot and
hashes them with eligible IDs and team-size limits. A changed hash marks the old
proposal stale without editing its membership. Cancellation and event start also
make the preview unavailable for further grouping. The UI displays stale status
when fetched or refreshed; it does not poll. Phase 4 revalidates the snapshot
under the event lock before finalization, even if the browser shows a fresh preview. Approved previews
remain immutable snapshots; current assignments are shown separately in the final roster.

Phase 4 adds finalization, but event completion is not implemented yet. Existing accounts
therefore start with empty history until later lifecycle work or trusted demo
fixtures supply completed memberships. The tests supply explicit historical
fixtures; proposals never become history simply because they were generated.

## Edge cases

| Case                              | Handling                                                                                                           |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| No registrations or below minimum | Typed error describing the missing minimum                                                                         |
| Unpartitionable count             | Explain that size limits or eligible count must change                                                             |
| Uneven participant count          | Balanced valid sizes, e.g. 10 people at 3–4 becomes 4, 3, 3                                                        |
| Unequal-size scoring              | Fix the size multiset before optimizing; candidates have equal pair opportunities                                  |
| No history/newcomer               | Missing pair frequencies are zero                                                                                  |
| Partial overlap                   | Prefer lower total weighted repeats, with honest heuristic explanations                                            |
| Everyone worked together          | Prefer the least frequent partnerships                                                                             |
| One person knows everyone         | Minimize frequency; distribute burden among equal-cost results                                                     |
| Equal histories                   | Seeded reproducible ties; no claim that one arbitrary tie is intrinsically fairer                                  |
| Waitlisted/cancelled registration | Excluded from eligible participants                                                                                |
| Pre-grouping withdrawal/promotion | Before finalization, Phase 4 permits withdrawal/promotion until event start; old previews become stale             |
| Registration/history changes      | Preserve old preview, flag stale, require regeneration                                                             |
| Concurrent/retried generation     | Event lock and unique request ID prevent duplicate retry results                                                   |
| Invalid/duplicate source data     | Run-level membership uniqueness, composite team/run foreign key, finalized-run uniqueness, distinct event counting |
| Over 100 eligible people          | Reject clearly; never silently omit participants                                                                   |
| Large teams                       | Reduce neighbor attempts using a deterministic pair-work budget                                                    |
| Sensitive history                 | Owner-only proposed names and aggregate scores; no emails or unrelated historical rosters in responses             |

Skill balancing, availability matching, and mandatory/prohibited participant pairs
need explicit product rules and are excluded. Post-finalization dropouts,
confirmation declines, and replacements are described in the Phase 4 team lifecycle.

## Verification and recovery

Engine tests include hand calculations, small exact-optimum fixtures, Hypothesis
invariants, impossible sizes, equal/partial/dense histories, and the random
baseline comparison. PostgreSQL tests cover history filtering, eligibility,
ownership/CSRF, time boundaries, rollback, constraints, stale inputs, and concurrent
retries. Browser tests cover early-generation errors, history-aware previews,
lost-response retry, persistence, stale display, and infeasible regeneration.

The migration adds proposal/history tables and lifecycle constraint values; it
does not change existing registrations. Back up proposal data before downgrading:
downgrade deletes those tables and restores `GROUPS_PROPOSED` events to `PUBLISHED`.
Later lifecycle states must be resolved before restoring the old event constraint;
the downgrade refuses to silently reopen completed events.
