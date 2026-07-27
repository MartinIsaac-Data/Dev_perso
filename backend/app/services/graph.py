"""Directed acyclic graph primitives for the skill graph.

These are pure functions over `(node, node)` edge pairs — no SQLAlchemy, no
session, no database. That is deliberate: graph logic is the part of this
application most likely to be wrong in a subtle way, and pure functions can be
tested exhaustively against hand-built graphs in microseconds.

The alternative considered and rejected was doing this in SQL with recursive
CTEs. Recursive CTEs are the right tool for *reading* a tree back in one query
(and the cause tree in the Business Case Lab does exactly that), but they are
a poor tool for cycle detection: a recursive CTE over a cyclic graph does not
report the cycle, it runs until it hits a row limit. Detecting the cycle and
naming the nodes involved needs a traversal that remembers its own stack.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Hashable, Iterable, Sequence
from typing import TypeVar

N = TypeVar("N", bound=Hashable)


class CycleError(ValueError):
    """Raised when a supposedly acyclic graph contains a cycle."""

    def __init__(self, cycle: Sequence[object]) -> None:
        self.cycle = list(cycle)
        rendered = " -> ".join(str(n) for n in self.cycle)
        super().__init__(f"skill graph contains a cycle: {rendered}")


def build_adjacency(edges: Iterable[tuple[N, N]]) -> dict[N, set[N]]:
    """Map each node to the set of nodes that depend on it."""
    adjacency: dict[N, set[N]] = defaultdict(set)
    for prerequisite, dependent in edges:
        adjacency[prerequisite].add(dependent)
        adjacency.setdefault(dependent, set())
    return dict(adjacency)


def find_cycle(edges: Iterable[tuple[N, N]]) -> list[N] | None:
    """Return one cycle as a node list, or None if the graph is acyclic.

    Iterative depth-first search with an explicit stack rather than recursion:
    the taxonomy is shallow today, but a recursive implementation would fail
    with a RecursionError on a pathological import rather than a clear message,
    and the whole point of this function is to produce a clear message.
    """
    adjacency = build_adjacency(edges)
    UNVISITED, IN_PROGRESS, DONE = 0, 1, 2
    state: dict[N, int] = dict.fromkeys(adjacency, UNVISITED)

    for root in adjacency:
        if state[root] != UNVISITED:
            continue
        # Each stack frame is (node, iterator over its remaining successors).
        path: list[N] = []
        stack: list[tuple[N, deque[N]]] = [(root, deque(sorted(adjacency[root], key=str)))]
        state[root] = IN_PROGRESS
        path.append(root)

        while stack:
            node, successors = stack[-1]
            if not successors:
                state[node] = DONE
                stack.pop()
                path.pop()
                continue
            nxt = successors.popleft()
            if state.get(nxt, UNVISITED) == IN_PROGRESS:
                # Found a back edge: the cycle is the tail of the current path.
                start = path.index(nxt)
                return [*path[start:], nxt]
            if state.get(nxt, UNVISITED) == UNVISITED:
                state[nxt] = IN_PROGRESS
                path.append(nxt)
                stack.append((nxt, deque(sorted(adjacency.get(nxt, set()), key=str))))
    return None


def assert_acyclic(edges: Iterable[tuple[N, N]]) -> None:
    edges = list(edges)
    cycle = find_cycle(edges)
    if cycle is not None:
        raise CycleError(cycle)


def topological_order(edges: Iterable[tuple[N, N]], nodes: Iterable[N] | None = None) -> list[N]:
    """Kahn's algorithm. Prerequisites always precede their dependents.

    Ties are broken by the string form of the node so the output is stable
    across runs — an unstable learning order would make two consecutive
    quarterly reviews disagree for no reason.
    """
    edges = list(edges)
    adjacency = build_adjacency(edges)
    all_nodes: set[N] = set(adjacency)
    if nodes is not None:
        all_nodes |= set(nodes)

    indegree: dict[N, int] = dict.fromkeys(all_nodes, 0)
    for _, dependent in edges:
        indegree[dependent] += 1

    ready = deque(sorted((n for n in all_nodes if indegree[n] == 0), key=str))
    order: list[N] = []

    while ready:
        node = ready.popleft()
        order.append(node)
        newly_ready = []
        for dependent in sorted(adjacency.get(node, set()), key=str):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                newly_ready.append(dependent)
        # Re-sort the frontier so ordering does not depend on discovery order.
        ready = deque(sorted([*ready, *newly_ready], key=str))

    if len(order) != len(all_nodes):
        remaining = [n for n in all_nodes if n not in set(order)]
        cycle = find_cycle([(a, b) for a, b in edges if a in set(remaining)])
        raise CycleError(cycle or remaining)
    return order


def descendants(edges: Iterable[tuple[N, N]], node: N) -> set[N]:
    """Every node reachable downstream of `node`, excluding `node` itself.

    This is the number that matters for the critical path view: a skill that
    unlocks forty others is worth working on before one that unlocks two,
    regardless of how interesting either is.
    """
    adjacency = build_adjacency(edges)
    seen: set[N] = set()
    queue = deque(adjacency.get(node, set()))
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(adjacency.get(current, set()) - seen)
    seen.discard(node)
    return seen


def ancestors(edges: Iterable[tuple[N, N]], node: N) -> set[N]:
    """Every prerequisite upstream of `node`, transitively."""
    reversed_edges = [(b, a) for a, b in edges]
    return descendants(reversed_edges, node)


def blocking_scores(edges: Iterable[tuple[N, N]], blocked: Iterable[N]) -> dict[N, int]:
    """For each blocked node, how many other blocked nodes it holds up.

    `blocked` is the set of skills not yet at their required level. Counting
    only blocked descendants — rather than all descendants — is what makes
    this a *critical path* rather than a popularity contest: a prerequisite
    whose dependents are already satisfied blocks nothing, however central it
    looks in the taxonomy.
    """
    edges = list(edges)
    blocked_set = set(blocked)
    return {node: len(descendants(edges, node) & blocked_set) for node in blocked_set}
