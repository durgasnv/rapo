from itertools import combinations
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.grouping_engine import (
    ATTEMPTS,
    STEPS_PER_ATTEMPT,
    GroupingError,
    generate,
    pair_key,
    score,
    team_sizes,
)


def people(count: int) -> list[UUID]:
    return [UUID(int=i + 1) for i in range(count)]


@pytest.mark.parametrize(
    "count,minimum,maximum,expected",
    [
        (10, 3, 4, [4, 3, 3]),
        (12, 3, 4, [3, 3, 3, 3]),
        (5, 3, 5, [5]),
        (100, 1, 100, [1] * 100),
        (100, 50, 100, [50, 50]),
    ],
)
def test_balanced_sizes_are_chosen_before_history(count, minimum, maximum, expected):
    assert team_sizes(count, minimum, maximum) == expected


@pytest.mark.parametrize(
    "count,minimum,maximum,code",
    [
        (0, 3, 4, "no_participants"),
        (2, 3, 4, "too_few"),
        (7, 4, 4, "unpartitionable"),
        (101, 3, 5, "participant_limit"),
        (3, 0, 4, "invalid_sizes"),
        (3, 4, 3, "invalid_sizes"),
    ],
)
def test_actionable_infeasibility(count, minimum, maximum, code):
    with pytest.raises(GroupingError) as error:
        generate(people(count), minimum, maximum, {}, 0)
    assert error.value.code == code


def test_hand_calculated_score_and_fairness():
    a, b, c = people(3)
    assert score([[a, b, c]], {(a, b): 3, (b, c): 1}) == (4, 26)
    # Same primary cost, but the second arrangement distributes repeat burden.
    a, b, c, d, e, f = people(6)
    history = {(a, b): 2, (a, d): 1, (b, e): 1}
    assert score([[a, b, c], [d, e, f]], history) == (2, 8)
    assert score([[a, d, f], [b, c, e]], history) == (2, 4)


def test_partial_overlap_and_newcomers_find_zero_repeat_solution():
    ids = people(6)
    history = {pair_key(a, b): 4 for team in [ids[:3], ids[3:]] for a, b in combinations(team, 2)}
    result = generate(ids, 2, 2, history, 42)
    assert result.score == 0
    assert result.score <= result.baseline_score
    assert generate(ids, 2, 2, {}, 42).score == 0


def test_everyone_worked_together_prefers_low_frequency_and_matches_small_exact_optimum():
    ids = people(6)
    preferred = {pair_key(ids[i], ids[i + 1]) for i in range(0, 6, 2)}
    history = {
        pair_key(a, b): 1 if pair_key(a, b) in preferred else 10 for a, b in combinations(ids, 2)
    }
    result = generate(ids, 2, 2, history, 19)

    def exact(remaining):
        if not remaining:
            return 0
        a = remaining[0]
        return min(
            history[pair_key(a, b)] + exact([p for p in remaining[1:] if p != b])
            for b in remaining[1:]
        )

    assert result.score == exact(ids) == 3
    assert result.score < result.baseline_score
    assert all(history[pair_key(*team)] == 1 for team in result.teams)


def test_one_person_has_worked_with_everyone_and_equal_histories_are_reproducible():
    ids = people(8)
    history = {pair_key(ids[0], other): index + 1 for index, other in enumerate(ids[1:])}
    result = generate(ids, 2, 2, history, 2)
    assert result.score == 1
    equal = {pair_key(a, b): 1 for a, b in combinations(ids, 2)}
    assert generate(ids, 2, 2, equal, 12) == generate(list(reversed(ids)), 2, 2, equal, 12)


def test_invalid_inputs_are_rejected():
    a, b = people(2)
    with pytest.raises(GroupingError, match="unique"):
        generate([a, a], 1, 2, {}, 0)
    for history in [{(b, a): 1}, {(a, b): -1}]:
        with pytest.raises(GroupingError, match="ordered and nonnegative"):
            generate([a, b], 1, 2, history, 0)


@given(count=st.integers(0, 100), minimum=st.integers(1, 25), slack=st.integers(0, 15))
def test_partition_feasibility_matches_all_possible_team_counts(count, minimum, slack):
    maximum = minimum + slack
    possible = any(k * minimum <= count <= k * maximum for k in range(1, count + 1))
    if not possible:
        with pytest.raises(GroupingError):
            team_sizes(count, minimum, maximum)
    else:
        sizes = team_sizes(count, minimum, maximum)
        assert sum(sizes) == count
        assert max(sizes) - min(sizes) <= 1
        assert all(minimum <= size <= maximum for size in sizes)


@settings(max_examples=50, deadline=None)
@given(
    count=st.integers(1, 30),
    minimum=st.integers(1, 8),
    slack=st.integers(0, 5),
    seed=st.integers(0, 2147483647),
    data=st.data(),
)
def test_proposals_preserve_invariants_and_never_lose_to_baseline(
    count, minimum, slack, seed, data
):
    maximum = minimum + slack
    try:
        sizes = team_sizes(count, minimum, maximum)
    except GroupingError:
        return
    ids = people(count)
    pairs = list(combinations(ids, 2))
    weights = data.draw(st.lists(st.integers(0, 10), min_size=len(pairs), max_size=len(pairs)))
    history = dict(zip(pairs, weights, strict=True))
    result = generate(ids, minimum, maximum, history, seed)
    assert sorted(p for team in result.teams for p in team) == ids
    assert sorted(map(len, result.teams)) == sorted(sizes)
    assert score(result.teams, history) == (result.score, result.fairness)
    assert (result.score, result.fairness) <= (result.baseline_score, result.baseline_fairness)
    assert result.evaluations <= ATTEMPTS * STEPS_PER_ATTEMPT
    assert result == generate(list(reversed(ids)), minimum, maximum, history, seed)
