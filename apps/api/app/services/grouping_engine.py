"""Deterministic, bounded team proposals; independent of HTTP and persistence."""

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from uuid import UUID

ALGORITHM_VERSION = "balanced-greedy-v1"
MAX_PARTICIPANTS = 100
ATTEMPTS = 8
STEPS_PER_ATTEMPT = 256
PAIR_WORK_PER_ATTEMPT = 100_000
Pair = tuple[UUID, UUID]


class GroupingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def pair_key(a: UUID, b: UUID) -> Pair:
    return (a, b) if a < b else (b, a)


def team_sizes(count: int, minimum: int, maximum: int) -> list[int]:
    if minimum < 1 or maximum < minimum:
        raise GroupingError("invalid_sizes", "Team size limits are invalid.")
    if count == 0:
        raise GroupingError("no_participants", "No eligible participants. Wait for registrations.")
    if count > MAX_PARTICIPANTS:
        raise GroupingError("participant_limit", "Grouping currently supports at most 100 people.")
    teams = count // minimum
    if teams == 0:
        raise GroupingError(
            "too_few",
            f"Need at least {minimum} people; only {count} are eligible. Reschedule or "
            "change the team-size limits before regenerating.",
        )
    if teams * maximum < count:
        raise GroupingError(
            "unpartitionable",
            f"Cannot place all {count} people in teams of {minimum}–{maximum}. "
            "Change team-size limits or the eligible participant count before regenerating.",
        )
    size, remainder = divmod(count, teams)
    return [size + (index < remainder) for index in range(teams)]


def score(teams: Sequence[Sequence[UUID]], history: Mapping[Pair, int]) -> tuple[int, int]:
    """Primary: total frequency. Tie-break: squared per-person repeat burden."""
    total = fairness = 0
    for team in teams:
        burdens = dict.fromkeys(team, 0)
        for a, b in combinations(team, 2):
            cost = history.get(pair_key(a, b), 0)
            total += cost
            burdens[a] += cost
            burdens[b] += cost
        fairness += sum(value * value for value in burdens.values())
    return total, fairness


@dataclass(frozen=True)
class Proposal:
    teams: tuple[tuple[UUID, ...], ...]
    score: int
    fairness: int
    baseline_score: int
    baseline_fairness: int
    evaluations: int


def partition(people: list[UUID], sizes: list[int]) -> list[list[UUID]]:
    teams = []
    offset = 0
    for size in sizes:
        teams.append(people[offset : offset + size])
        offset += size
    return teams


def generate(
    participants: Sequence[UUID],
    minimum: int,
    maximum: int,
    history: Mapping[Pair, int],
    seed: int,
) -> Proposal:
    people = sorted(participants)
    if len(set(people)) != len(people):
        raise GroupingError("duplicate_participants", "Participants must be unique.")
    if any(a >= b or cost < 0 for (a, b), cost in history.items()):
        raise GroupingError("invalid_history", "Pair history must be ordered and nonnegative.")
    sizes = team_sizes(len(people), minimum, maximum)
    # Large teams make each neighbor expensive. Bound pair work deterministically
    # rather than using a wall-clock cutoff, which would break reproducibility.
    pairs = sum(size * (size - 1) // 2 for size in sizes)
    steps = min(STEPS_PER_ATTEMPT, max(1, PAIR_WORK_PER_ATTEMPT // max(1, pairs)))
    rng = random.Random(seed)
    shuffled = people.copy()
    rng.shuffle(shuffled)
    best = partition(shuffled, sizes)
    baseline = best_score = score(best, history)
    evaluations = 0
    for _ in range(ATTEMPTS):
        if best_score == (0, 0):
            break
        shuffled = people.copy()
        rng.shuffle(shuffled)
        teams: list[list[UUID]] = [[] for _ in sizes]
        for person in shuffled:
            available = [i for i, team in enumerate(teams) if len(team) < sizes[i]]
            rng.shuffle(available)
            chosen = min(
                available,
                key=lambda i: sum(history.get(pair_key(person, other), 0) for other in teams[i]),
            )
            teams[chosen].append(person)
        current = score(teams, history)
        if current < best_score:
            best, best_score = [team.copy() for team in teams], current
        if len(teams) < 2:
            break
        for _ in range(steps):
            if best_score == (0, 0):
                break
            i, j = rng.sample(range(len(teams)), 2)
            a, b = teams[i], teams[j]
            x, y = rng.randrange(len(a)), rng.randrange(len(b))
            # A move is allowed only when it exchanges the two balanced sizes.
            move = len(a) == len(b) + 1 and rng.randrange(2) == 0
            next_a, next_b = a.copy(), b.copy()
            if move:
                next_b.append(next_a.pop(x))
            else:
                next_a[x], next_b[y] = next_b[y], next_a[x]
            old = score([a, b], history)
            new = score([next_a, next_b], history)
            candidate = (current[0] - old[0] + new[0], current[1] - old[1] + new[1])
            evaluations += 1
            if candidate < current:
                teams[i], teams[j], current = next_a, next_b, candidate
                if current < best_score:
                    best, best_score = [team.copy() for team in teams], current
    canonical = tuple(sorted(tuple(sorted(team)) for team in best))
    assert sorted(person for team in canonical for person in team) == people
    assert all(minimum <= len(team) <= maximum for team in canonical)
    return Proposal(canonical, *best_score, *baseline, evaluations)
