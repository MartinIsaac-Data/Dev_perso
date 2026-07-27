"""Graph primitives.

These are the functions every downstream skill query depends on, so they are
tested against hand-built graphs where the right answer is obvious by
inspection, not against the real taxonomy where a wrong answer would be
plausible.
"""

from __future__ import annotations

import pytest

from app.services.graph import (
    CycleError,
    ancestors,
    assert_acyclic,
    blocking_scores,
    descendants,
    find_cycle,
    topological_order,
)

# a -> b -> d
#  \-> c -/
DIAMOND = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]

CHAIN = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")]


class TestCycleDetection:
    def test_acyclic_graphs_report_no_cycle(self) -> None:
        assert find_cycle(DIAMOND) is None
        assert find_cycle(CHAIN) is None
        assert find_cycle([]) is None

    def test_detects_two_node_cycle(self) -> None:
        cycle = find_cycle([("a", "b"), ("b", "a")])
        assert cycle is not None
        assert cycle[0] == cycle[-1], "cycle must be reported as a closed walk"
        assert set(cycle) == {"a", "b"}

    def test_detects_long_cycle(self) -> None:
        cycle = find_cycle([("a", "b"), ("b", "c"), ("c", "d"), ("d", "b")])
        assert cycle is not None
        assert set(cycle) == {"b", "c", "d"}
        assert "a" not in cycle, "the tail leading into the cycle is not part of it"

    def test_detects_cycle_reachable_only_from_a_later_root(self) -> None:
        # The traversal must not stop after exhausting the first root.
        edges = [("root1", "x"), ("root2", "p"), ("p", "q"), ("q", "p")]
        cycle = find_cycle(edges)
        assert cycle is not None
        assert set(cycle) == {"p", "q"}

    def test_shared_subtree_is_not_a_cycle(self) -> None:
        # Two paths reaching the same node is a diamond, not a cycle. A naive
        # "already seen" check would report this incorrectly.
        assert find_cycle(DIAMOND) is None

    def test_assert_acyclic_raises_with_the_cycle_named(self) -> None:
        with pytest.raises(CycleError) as excinfo:
            assert_acyclic([("a", "b"), ("b", "a")])
        assert "a" in str(excinfo.value)
        assert excinfo.value.cycle


class TestTopologicalOrder:
    def test_prerequisites_precede_dependents(self) -> None:
        order = topological_order(DIAMOND)
        position = {node: i for i, node in enumerate(order)}
        for prerequisite, dependent in DIAMOND:
            assert position[prerequisite] < position[dependent]

    def test_includes_isolated_nodes(self) -> None:
        order = topological_order(DIAMOND, nodes=["lonely"])
        assert "lonely" in order
        assert len(order) == 5

    def test_is_deterministic(self) -> None:
        # Two runs over the same graph, edges shuffled, must agree. An
        # unstable order would make consecutive reviews recommend different
        # next steps for no reason.
        assert topological_order(DIAMOND) == topological_order(list(reversed(DIAMOND)))

    def test_raises_on_cycle(self) -> None:
        with pytest.raises(CycleError):
            topological_order([("a", "b"), ("b", "a")])


class TestReachability:
    def test_descendants_are_transitive(self) -> None:
        assert descendants(CHAIN, "a") == {"b", "c", "d", "e"}
        assert descendants(CHAIN, "d") == {"e"}
        assert descendants(CHAIN, "e") == set()

    def test_descendants_excludes_the_node_itself(self) -> None:
        assert "a" not in descendants(DIAMOND, "a")

    def test_ancestors_are_the_mirror_of_descendants(self) -> None:
        assert ancestors(CHAIN, "e") == {"a", "b", "c", "d"}
        assert ancestors(DIAMOND, "d") == {"a", "b", "c"}


class TestBlockingScores:
    def test_counts_only_blocked_descendants(self) -> None:
        # `c` is already at level, so `a` blocks b and d only.
        scores = blocking_scores(DIAMOND, blocked={"a", "b", "d"})
        assert scores["a"] == 2
        assert scores["b"] == 1
        assert scores["d"] == 0

    def test_a_skill_whose_dependents_are_satisfied_blocks_nothing(self) -> None:
        # This is the property that makes the view a critical path rather
        # than a popularity ranking of the taxonomy.
        scores = blocking_scores(CHAIN, blocked={"a"})
        assert scores == {"a": 0}

    def test_deep_chain_attributes_the_whole_tail_to_the_root(self) -> None:
        scores = blocking_scores(CHAIN, blocked={"a", "b", "c", "d", "e"})
        assert scores["a"] == 4
        assert scores["c"] == 2
        assert scores["e"] == 0
