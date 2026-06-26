"""L1 : résolution de Sudoku par multiples solveurs.

Five solving paradigms (backtracking, Dancing Links, CP-SAT, SAT, genetic)
behind a common ``Solver`` interface, with a benchmark harness and report
generator.
"""

from .board import Grid
from .metrics import SolveResult

__all__ = ["Grid", "SolveResult"]
__version__ = "0.1.0"
