"""Abstract base class shared by every Sudoku solver."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..board import Grid
from ..instrument import measure
from ..metrics import SolveResult


class Solver(ABC):
    """Common interface for all Sudoku solvers.

    Subclasses implement :meth:`_solve`, returning the solved grid (or ``None``)
    and an optional node count. The public :meth:`solve` wraps that call with
    timing and peak-memory instrumentation and packages a :class:`SolveResult`.
    """

    #: Stable, CLI-friendly identifier.
    name: str = "solver"

    #: Whether the solver can enumerate multiple solutions via :meth:`solve_all`.
    supports_multi: bool = False

    def solve(self, grid: Grid, track_memory: bool = True) -> SolveResult:
        """Solve ``grid`` and return an instrumented :class:`SolveResult`."""
        with measure(track_memory=track_memory) as m:
            solution, nodes, extra = self._solve(grid)
        solved = solution is not None and solution.is_solved()
        return SolveResult(
            solver=self.name,
            solved=solved,
            solution=solution if solved else None,
            elapsed_s=m.elapsed_s,
            nodes=nodes,
            peak_mem_bytes=m.peak_mem_bytes if track_memory else None,
            extra=extra or {},
        )

    @abstractmethod
    def _solve(self, grid: Grid):
        """Return ``(solution_or_None, nodes_or_None, extra_dict_or_None)``."""
        raise NotImplementedError

    def solve_all(self, grid: Grid, limit: int = 2) -> List[Grid]:
        """Enumerate up to ``limit`` solutions. Only meaningful when
        :attr:`supports_multi` is True; the default raises."""
        raise NotImplementedError(f"{self.name} does not support enumeration")
