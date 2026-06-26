"""SAT solver using a boolean CNF encoding and PySAT (Glucose3).

We use the classic 9x9x9 encoding: variable ``v(r, c, d)`` is true iff cell
(r, c) holds digit d. Clauses enforce:

* at-least-one digit per cell, plus at-most-one (cell uniqueness);
* each digit appears at-least / at-most once per row, column and box.

The "extended" encoding adds the redundant at-least-one clauses for row/col/box
(they are implied but often speed up unit propagation). ``nodes`` is reported as
the solver's conflict count.
"""

from __future__ import annotations

from typing import List

from ..board import EMPTY, N, Grid
from .base import Solver


def _var(r: int, c: int, d: int) -> int:
    """1-based DIMACS variable id for "cell (r,c) holds digit d" (d in 1..9)."""
    return r * 81 + c * 9 + (d - 1) + 1


def _at_most_one(lits: List[int]) -> List[List[int]]:
    """Pairwise at-most-one encoding for a list of literals."""
    clauses = []
    for i in range(len(lits)):
        for j in range(i + 1, len(lits)):
            clauses.append([-lits[i], -lits[j]])
    return clauses


def build_clauses(grid: Grid, extended: bool = True) -> List[List[int]]:
    clauses: List[List[int]] = []

    # Cell: exactly one digit.
    for r in range(N):
        for c in range(N):
            lits = [_var(r, c, d) for d in range(1, 10)]
            clauses.append(lits[:])                 # at least one
            clauses.extend(_at_most_one(lits))      # at most one

    # Rows, columns, boxes: each digit at most once (and optionally at least once).
    for d in range(1, 10):
        for r in range(N):
            lits = [_var(r, c, d) for c in range(N)]
            if extended:
                clauses.append(lits[:])
            clauses.extend(_at_most_one(lits))
        for c in range(N):
            lits = [_var(r, c, d) for r in range(N)]
            if extended:
                clauses.append(lits[:])
            clauses.extend(_at_most_one(lits))
        for br in range(0, N, 3):
            for bc in range(0, N, 3):
                lits = [
                    _var(br + dr, bc + dc, d)
                    for dr in range(3)
                    for dc in range(3)
                ]
                if extended:
                    clauses.append(lits[:])
                clauses.extend(_at_most_one(lits))

    # Givens as unit clauses.
    for r in range(N):
        for c in range(N):
            v = grid.at(r, c)
            if v != EMPTY:
                clauses.append([_var(r, c, v)])
    return clauses


def _model_to_grid(model) -> Grid:
    """Decode a satisfying assignment into a :class:`Grid`."""
    pos = set(lit for lit in model if lit > 0)
    cells = [EMPTY] * 81
    for r in range(N):
        for c in range(N):
            for d in range(1, 10):
                if _var(r, c, d) in pos:
                    cells[r * 9 + c] = d
                    break
    return Grid(tuple(cells))


class SatSolver(Solver):
    name = "sat"
    supports_multi = True

    def __init__(self, extended: bool = True):
        self.extended = extended

    def _solve(self, grid: Grid):
        from pysat.solvers import Glucose3

        clauses = build_clauses(grid, extended=self.extended)
        with Glucose3(bootstrap_with=clauses, use_timer=False) as solver:
            sat = solver.solve()
            stats = solver.accum_stats()
            nodes = int(stats.get("conflicts", 0)) if stats else None
            if not sat:
                return None, nodes, {"num_clauses": len(clauses)}
            solution = _model_to_grid(solver.get_model())
        return solution, nodes, {"num_clauses": len(clauses)}

    def solve_all(self, grid: Grid, limit: int = 2) -> List[Grid]:
        """Enumerate up to ``limit`` solutions via blocking clauses.

        After each model is found we add the clause negating its 81 cell-digit
        literals, forbidding that exact assignment so the next ``solve`` returns
        a different solution (or reports UNSAT once they are exhausted).
        """
        from pysat.solvers import Glucose3

        clauses = build_clauses(grid, extended=self.extended)
        solutions: List[Grid] = []
        with Glucose3(bootstrap_with=clauses, use_timer=False) as solver:
            while len(solutions) < limit and solver.solve():
                sol = _model_to_grid(solver.get_model())
                solutions.append(sol)
                block = [
                    -_var(r, c, sol.at(r, c)) for r in range(N) for c in range(N)
                ]
                solver.add_clause(block)
        return solutions
