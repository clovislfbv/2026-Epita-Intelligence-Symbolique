"""
Extension Verification for Dung Argumentation Frameworks
=========================================================
Three predicate functions that check whether a given set of arguments
is a grounded / preferred / stable extension of an AF.

Definitions (Dung, 1995)
-------------------------
Let AF = (Args, Attacks), S ⊆ Args, S⁺ = {b | ∃a∈S, (a,b)∈Attacks}.

Conflict-free : S ∩ S⁺ = ∅
Defends(S, a) : attackers(a) ⊆ S⁺
Admissible    : conflict-free ∧ ∀a∈S, Defends(S, a)
Complete      : admissible ∧ {a | Defends(S,a)} ⊆ S
Grounded      : the least fixed point of the characteristic function F_AF,
                equivalently the unique minimal complete extension.
Preferred     : maximal (⊆) admissible set.
Stable        : conflict-free ∧ S⁺ = Args \\ S.
"""

import networkx as nx



def is_complete(graph: nx.DiGraph, extension: set) -> bool:
    """
    Return True iff `extension` is a complete extension of `graph`.
    """
    S = frozenset(extension)
    if not _is_admissible(graph, S):
        return False
    return _characteristic_function(graph, S) == S

# ---------------------------------------------------------------------------
# Shared AF helpers
# ---------------------------------------------------------------------------

def _attacked_by(graph: nx.DiGraph, S: frozenset) -> frozenset:
    """All arguments attacked by at least one member of S."""
    return frozenset(v for u in S for v in graph.successors(u))


def _is_conflict_free(graph: nx.DiGraph, S: frozenset) -> bool:
    return S.isdisjoint(_attacked_by(graph, S))


def _is_admissible(graph: nx.DiGraph, S: frozenset) -> bool:
    if not _is_conflict_free(graph, S):
        return False
    atk_by_S = _attacked_by(graph, S)
    return all(
        frozenset(graph.predecessors(a)).issubset(atk_by_S)
        for a in S
    )


def _characteristic_function(graph: nx.DiGraph, S: frozenset) -> frozenset:
    """
    F_AF(S) = { a ∈ Args | S defends a }
    The grounded extension is the least fixed point of F_AF starting from ∅.
    """
    all_args = frozenset(graph.nodes())
    atk_by_S = _attacked_by(graph, S)
    return frozenset(
        a for a in all_args
        if frozenset(graph.predecessors(a)).issubset(atk_by_S)
    )


def _grounded_extension(graph: nx.DiGraph) -> frozenset:
    """Compute the grounded extension via iterated F_AF from ∅ (O(n²+nm))."""
    current = frozenset()
    while True:
        nxt = _characteristic_function(graph, current)
        if nxt == current:
            return current
        current = nxt


# ---------------------------------------------------------------------------
# Public verification functions
# ---------------------------------------------------------------------------

def is_stable(graph: nx.DiGraph, extension: set) -> bool:
    """
    Return True iff `extension` is a stable extension of `graph`.

    A stable extension is a conflict-free set S such that every argument
    outside S is attacked by S  (S⁺ = Args \\ S).

    Complexity: O(n + m)
    """
    S = frozenset(extension)
    all_args = frozenset(graph.nodes())

    if not _is_conflict_free(graph, S):
        return False

    outside = all_args - S
    return outside.issubset(_attacked_by(graph, S))


def is_preferred(graph: nx.DiGraph, extension: set) -> bool:
    """
    Return True iff `extension` is a preferred extension of `graph`.

    A preferred extension is a maximal (w.r.t. ⊆) admissible set: it is
    admissible and no admissible strict superset exists.

    Strategy
    --------
    1. Check admissibility in O(n + m).
    2. For maximality, check that no outside argument `a` can be added to S
       while keeping S ∪ {a} admissible.  S ∪ {a} is admissible iff:
         (a) conflict-free : a ∉ atk_by_S  and  successors(a) ∩ S = ∅
         (b) S ∪ {a} defends a : attackers(a) ⊆ atk_by_S ∪ successors(a)
             (S already defends its own members — adding an outside argument
              cannot create new threats against existing members of S.)

    All three tests use only atk_by_S (precalculated once) and per-node
    adjacency lookups → O(n + m) total.

    Complexity: O(n + m)
    """
    S = frozenset(extension)
    all_args = frozenset(graph.nodes())

    if not _is_admissible(graph, S):
        return False

    atk_by_S = _attacked_by(graph, S)   # computed once

    for a in all_args - S:
        # (a) conflict-free: S must not attack a, a must not attack S,
        #     and a must not self-attack
        if a in atk_by_S:
            continue
        successors_a = frozenset(graph.successors(a))
        if not successors_a.isdisjoint(S):
            continue
        if a in successors_a:          # self-attacking: never admissible
            continue

        # (b) S ∪ {a} defends a:
        #     every attacker of a must be attacked by S or by a itself
        attackers_a = frozenset(graph.predecessors(a))
        if attackers_a.issubset(atk_by_S | successors_a):
            # a can be added while preserving admissibility → S not maximal
            return False

    return True


def is_grounded(graph: nx.DiGraph, extension: set) -> bool:
    """
    Return True iff `extension` is the grounded extension of `graph`.

    The grounded extension is the unique least fixed point of the
    characteristic function F_AF(S) = {a | S defends a}, computed
    iteratively from ∅.  It is the smallest complete extension.

    Since the grounded extension is unique, the check simply computes it
    and compares.

    Complexity: O(n² + nm)  — at most n iterations of F_AF, each O(n+m).
    """
    return frozenset(extension) == _grounded_extension(graph)


# ---------------------------------------------------------------------------
# Self-tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    def check(label, got, expected):
        mark = "✓" if got == expected else "✗"
        print(f"  {mark} {label}: {got}  (expected {expected})")

    # ── AF1: no attacks ─────────────────────────────────────────────────
    print("\nAF1 — no attacks {a, b, c}")
    g = nx.DiGraph()
    g.add_nodes_from(["a", "b", "c"])
    check("is_grounded ({a,b,c})",  is_grounded(g,  {"a","b","c"}), True)
    check("is_preferred({a,b,c})",  is_preferred(g, {"a","b","c"}), True)
    check("is_stable   ({a,b,c})",  is_stable(g,    {"a","b","c"}), True)
    check("is_grounded ({})",        is_grounded(g,  set()),          False)
    check("is_preferred({})",        is_preferred(g, set()),          False)

    # ── AF2: even cycle a ↔ b ───────────────────────────────────────────
    print("\nAF2 — even cycle a ↔ b")
    g = nx.DiGraph()
    g.add_edges_from([("a","b"),("b","a")])
    check("is_grounded ({})",   is_grounded(g,  set()),   True)
    check("is_grounded ({a})",  is_grounded(g,  {"a"}),   False)
    check("is_preferred({a})",  is_preferred(g, {"a"}),   True)
    check("is_preferred({b})",  is_preferred(g, {"b"}),   True)
    check("is_preferred({})",   is_preferred(g, set()),   False)
    check("is_stable   ({a})",  is_stable(g,    {"a"}),   True)
    check("is_stable   ({b})",  is_stable(g,    {"b"}),   True)
    check("is_stable   ({})",   is_stable(g,    set()),   False)

    # ── AF3: odd cycle a→b→c→a ──────────────────────────────────────────
    print("\nAF3 — odd cycle a→b→c→a (no stable extension)")
    g = nx.DiGraph()
    g.add_edges_from([("a","b"),("b","c"),("c","a")])
    check("is_grounded ({})",        is_grounded(g,  set()),          True)
    check("is_stable   ({a})",       is_stable(g,    {"a"}),          False)
    check("is_stable   ({a,b,c})",   is_stable(g,    {"a","b","c"}),  False)

    # ── AF4: Nixon diamond a↔b, b↔c ─────────────────────────────────────
    print("\nAF4 — Nixon diamond: a↔b, b↔c")
    g = nx.DiGraph()
    g.add_edges_from([("a","b"),("b","a"),("b","c"),("c","b")])
    check("is_grounded ({})",      is_grounded(g,  set()),       True)
    check("is_preferred({a,c})",   is_preferred(g, {"a","c"}),   True)
    check("is_preferred({b})",     is_preferred(g, {"b"}),       True)
    check("is_preferred({})",      is_preferred(g, set()),       False)
    check("is_stable   ({a,c})",   is_stable(g,    {"a","c"}),   True)
    check("is_stable   ({b})",     is_stable(g,    {"b"}),       True)

    # ── AF5: chain a→b→c ────────────────────────────────────────────────
    print("\nAF5 — chain a→b→c")
    g = nx.DiGraph()
    g.add_edges_from([("a","b"),("b","c")])
    check("is_grounded ({a,c})",   is_grounded(g,  {"a","c"}),  True)
    check("is_preferred({a,c})",   is_preferred(g, {"a","c"}),  True)
    check("is_stable   ({a,c})",   is_stable(g,    {"a","c"}),  True)
    check("is_grounded ({a})",     is_grounded(g,  {"a"}),      False)
    check("is_preferred({a})",     is_preferred(g, {"a"}),      False)

    # ── AF6: self-attack a→a ─────────────────────────────────────────────
    print("\nAF6 — self-attack a→a")
    g = nx.DiGraph()
    g.add_edge("a","a")
    check("is_grounded ({})",   is_grounded(g,  set()),  True)
    check("is_preferred({})",   is_preferred(g, set()),  True)
    check("is_stable   ({})",   is_stable(g,    set()),  False)  # a not attacked

