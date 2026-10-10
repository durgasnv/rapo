# History-aware grouping

The engine in `apps/api/app/services/grouping_engine.py` is pure Python: no database,
HTTP, current clock, or global random generator. Its inputs are eligible UUIDs,
minimum/maximum size, ordered pair frequencies, and an integer seed.

## Choose sizes first

For `N` people, choose the largest team count `k = floor(N / minimum)`.
It is feasible only when `k > 0` and `N <= k * maximum`. Distribute the remainder
so team sizes differ by at most one. Every generated assignment covers every
eligible person exactly once.

This policy favors more, smaller teams within the organizer's limits. It is an
explicit product choice, independent of history. For example, 12 people at 3–4
become four teams of three rather than three teams of four. Fixing the size
multiset also fixes the number of within-team pair opportunities, so the search
cannot improve a score merely by choosing more teams. Moves may exchange which
team has the larger size, but preserve that multiset.

## Compare candidates

For team `T`, add each unordered pair's completed-event count:

`repeat_cost(T) = sum(history[a,b] for a,b in pairs(T))`

The primary objective is the sum across all teams. Each participant's repeat
burden is the sum of their pair costs within their team. Among candidates with
equal total cost, minimize the sum of squared burdens across participants. This
discourages concentrating repeats on a few people without sacrificing the primary
objective. Missing history contributes zero.

Example: Alice–Bob has count 3, Alice–Carol 0, Bob–Carol 1. The team cost is 4.
Individual burdens are 3, 4, 1, giving fairness penalty `9 + 16 + 1 = 26`.

## Search and bounds

1. Sort IDs, then shuffle using a local seeded generator. Partition this random
   baseline using the chosen sizes and retain it as an initial valid solution.
2. For up to eight starts, shuffle people and greedily place each person where
   their incremental repeat cost is smallest, respecting the chosen capacities.
3. Sample member swaps and moves. Accept only strict lexicographic improvements
   to `(repeat_cost, fairness_penalty)` while preserving balanced valid sizes.
4. Retain the best candidate across starts, including the baseline. Stop early
   when cost and fairness are zero. Canonicalize output order by participant IDs.

There are at most 256 sampled neighbors per start. For large teams this decreases
to `max(1, floor(100000 / within_team_pair_count))`, capped at 256. Combined with
the 100-person input limit, this bounds work without a machine-dependent clock
cutoff. Reproducibility includes the algorithm version; changing the budget or
search changes that version for subsequent algorithm releases.

The greedy construction performs quadratic pair lookups per start. Neighbor
evaluation rescans the two affected teams, with worst-case quadratic work per
neighbor. There is no exhaustive search in production, no global optimality
claim, and no proof that repeats in the selected proposal are unavoidable.
Small hand-built fixtures are compared with brute-force optima in tests.

The initial cap keeps generation synchronous. Larger events and longer searches
need an asynchronous job with progress reporting before raising the cap. The
best valid candidate found is always retained; returned scores never lose to the
saved random baseline under the lexicographic objective.
