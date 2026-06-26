"""Constraint-programming solver using OR-Tools CP-SAT.

Each cell is an integer variable in 1..9 with three families of global
``AllDifferent`` constraints (rows, columns, boxes). CP-SAT reports the number
of branches explored, which we surface as the node count.
"""

from __future__ import annotations

from typing import List

from ..board import EMPTY, N, Grid
from .base import Solver


def _stat(solver, *names):
    """Read a CP-SAT statistic across OR-Tools versions (property or method)."""
    for name in names:
        if hasattr(solver, name):
            attr = getattr(solver, name)
            return attr() if callable(attr) else attr
    return 0


class CpSatSolver(Solver):
    name = "cp_sat"
    supports_multi = True

    def _solve(self, grid: Grid):
        from ortools.sat.python import cp_model

        model, x = self._build_model(grid)
        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        nodes = int(_stat(solver, "NumBranches", "num_branches"))
        extra = {
            "conflicts": int(_stat(solver, "NumConflicts", "num_conflicts")),
            "status": solver.StatusName(status),
        }
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None, nodes, extra
        cells = [solver.Value(x[r][c]) for r in range(N) for c in range(N)]
        return Grid(tuple(cells)), nodes, extra

    def solve_all(self, grid: Grid, limit: int = 2) -> List[Grid]:
        from ortools.sat.python import cp_model

        model, x = self._build_model(grid)

        class _Collector(cp_model.CpSolverSolutionCallback):
            def __init__(self):
                super().__init__()
                self.solutions: List[Grid] = []

            def on_solution_callback(self) -> None:
                cells = [self.Value(x[r][c]) for r in range(N) for c in range(N)]
                self.solutions.append(Grid(tuple(cells)))
                if len(self.solutions) >= limit:
                    self.StopSearch()

        solver = cp_model.CpSolver()
        solver.parameters.enumerate_all_solutions = True
        collector = _Collector()
        solver.Solve(model, collector)
        return collector.solutions

    def _build_model(self, grid: Grid):
        from ortools.sat.python import cp_model

        model = cp_model.CpModel()
        x = [[model.NewIntVar(1, 9, f"x_{r}_{c}") for c in range(N)] for r in range(N)]
        for r in range(N):
            for c in range(N):
                v = grid.at(r, c)
                if v != EMPTY:
                    model.Add(x[r][c] == v)
        for r in range(N):
            model.AddAllDifferent(x[r])
        for c in range(N):
            model.AddAllDifferent([x[r][c] for r in range(N)])
        for br in range(0, N, 3):
            for bc in range(0, N, 3):
                model.AddAllDifferent(
                    [x[br + dr][bc + dc] for dr in range(3) for dc in range(3)]
                )
        return model, x
