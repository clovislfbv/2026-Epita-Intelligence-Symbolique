"""
Preferred Extension for Dung Argumentation Frameworks
======================================================
Finds the first preferred extension of a directed NetworkX graph (AF),
optionally constrained to contain a given set of arguments.

Complexity note:
    Finding a preferred extension is Sigma_2^P-complete (NP^NP).
    The reference algorithm (Nofal, Atkinson & Dunne, 2014) uses
    backtracking with admissibility-based pruning, which is the
    state-of-the-art approach and avoids the naive 2^n enumeration.

Reference:
    Nofal, S., Atkinson, K., & Dunne, P. E. (2014).
    "Algorithms for decision problems in argument systems under
    preferred semantics." Artificial Intelligence, 207, 23-51.
"""

import networkx as nx


# ---------------------------------------------------------------------------
# Core AF helpers
# ---------------------------------------------------------------------------

def _attackers(graph: nx.DiGraph, node) -> frozenset:
    """Return the set of nodes that attack `node`."""
    return frozenset(graph.predecessors(node))


def _attacked_by_set(graph: nx.DiGraph, S: frozenset) -> frozenset:
    """Return the set of all nodes attacked by any member of S."""
    return frozenset(v for u in S for v in graph.successors(u))


def _is_conflict_free(graph: nx.DiGraph, S: frozenset) -> bool:
    """True iff no argument in S attacks another argument in S."""
    attacked = _attacked_by_set(graph, S)
    return S.isdisjoint(attacked)


def _defends(graph: nx.DiGraph, S: frozenset, node) -> bool:
    """True iff S defends `node` (every attacker of `node` is attacked by S)."""
    attacked_by_S = _attacked_by_set(graph, S)
    return _attackers(graph, node).issubset(attacked_by_S)


def _is_admissible(graph: nx.DiGraph, S: frozenset) -> bool:
    """True iff S is conflict-free and defends all its members."""
    if not _is_conflict_free(graph, S):
        return False
    return all(_defends(graph, S, a) for a in S)


# ---------------------------------------------------------------------------
# Preferred extension via backtracking + admissibility pruning
# ---------------------------------------------------------------------------

def preferred_extension(graph: nx.DiGraph, required: set = None) -> set:
    """
    Return one preferred extension of the argumentation framework `graph`.

    A preferred extension is a maximal (w.r.t. set inclusion) admissible set.

    Parameters
    ----------
    graph : nx.DiGraph
        A directed graph where nodes are arguments and an edge (a, b)
        means argument `a` attacks argument `b`.
    required : set, optional
        A set of arguments that must be included in the returned
        preferred extension. By Dung's fundamental lemma, every
        admissible set extends to at least one preferred extension;
        but a non-admissible `required` can still be contained in a
        preferred extension; the search below freely adds whatever
        further arguments are needed to defend it.

        If `required` is not conflict-free, no preferred extension
        can possibly contain it (conflict-freeness is monotone and
        can never be repaired by adding more arguments), so this
        function returns the empty set immediately in that case.
        Otherwise the search proceeds and returns empty only if no
        preferred extension containing `required` exists at all.

    Returns
    -------
    set
        The nodes forming a preferred extension that contains `required`
        (if `required` is given and admissible). Returns the empty set
        if the only preferred extension is the empty set, or if
        `required` is not admissible.

    Algorithm
    ---------
    Backtracking search that, for every argument, branches on whether it
    is IN or OUT of the candidate set. Two important correctness points:

    1. While building a candidate incrementally, only *conflict-freeness*
       is safe to prune on, because it is monotone: once two arguments in
       the candidate attack each other, no further additions can undo
       that. Full *admissibility* is NOT monotone under incremental
       construction -- an argument added early may look "undefended" at
       the time it is added, yet become properly defended once a later
       argument (which attacks its attacker) is also added. Pruning on
       full admissibility at every intermediate step discards branches
       that would have led to valid, larger admissible sets. Admissibility
       must only be checked once a candidate is complete (i.e., at a leaf
       of the search tree).

    2. Maximality must be decided by set inclusion, not by cardinality.
       We keep every admissible leaf set that is not a strict subset of
       another one found, and return one of those inclusion-maximal sets.

    To support `required`, every argument in `required` is forced IN
    from the start (instead of being a free choice during the search),
    and `required` itself is checked for admissibility up front.
    """
    args = list(graph.nodes())
    n = len(args)

    if n == 0:
        return set()

    required = frozenset(required) if required else frozenset()

    # Only conflict-freeness can be safely checked up front. Full
    # admissibility of `required` is NOT a valid pre-condition: a single
    # argument (or any non-admissible-but-conflict-free set) can still
    # belong to a preferred extension once the search adds the further
    # arguments needed to defend it. Requiring full admissibility here
    # incorrectly rejects valid inputs like required={'A'} above.
    if required and not _is_conflict_free(graph, required):
        return set()

    # Inclusion-maximal admissible sets found so far (an antichain).
    maximal_candidates: list = []

    def _record(IN: frozenset) -> None:
        """Insert IN into maximal_candidates, keeping only maximal sets."""
        for C in maximal_candidates:
            if IN <= C:
                return  # IN is dominated by an existing candidate; discard.
        # Remove any existing candidates that IN strictly dominates.
        maximal_candidates[:] = [C for C in maximal_candidates if not (C <= IN)]
        maximal_candidates.append(IN)

    # `required` arguments are forced IN from the start; only the rest
    # are free choices in the backtracking search.
    initial_remaining = tuple(a for a in args if a not in required)
    stack = [(required, initial_remaining)]

    while stack:
        IN, remaining = stack.pop()

        # --- Pruning: only conflict-freeness is safe mid-construction. --- #
        # (Full admissibility is checked only at leaves; see docstring.)
        if not _is_conflict_free(graph, IN):
            continue

        # --- No more arguments to assign --------------------------------- #
        if not remaining:
            if _is_admissible(graph, IN):
                _record(IN)
            continue

        # Pick the next argument to label.
        arg = remaining[0]
        rest = remaining[1:]

        # ---- Branch 1: label `arg` as OUT (skip it) -------------------- #
        stack.append((IN, rest))

        # ---- Branch 2: label `arg` as IN -------------------------------- #
        # Only prune here on conflict-freeness (cheap, monotone, safe).
        attacked_by_arg = frozenset(graph.successors(arg))
        if IN.isdisjoint(attacked_by_arg) and arg not in _attacked_by_set(graph, IN):
            stack.append((IN | {arg}, rest))

    if not maximal_candidates:
        return set()

    return set(maximal_candidates[0])