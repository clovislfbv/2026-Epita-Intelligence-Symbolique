"""Sudoku solver implementations behind a common :class:`Solver` interface."""

from __future__ import annotations

from typing import Dict, Type

from .base import Solver
from .backtracking import BacktrackingSolver
from .dancing_links import DancingLinksSolver
from .cp_sat import CpSatSolver
from .sat import SatSolver
from .genetic import GeneticSolver

#: Registry mapping CLI-friendly names to solver classes.
SOLVERS: Dict[str, Type[Solver]] = {
    "backtracking": BacktrackingSolver,
    "dlx": DancingLinksSolver,
    "cp_sat": CpSatSolver,
    "sat": SatSolver,
    "genetic": GeneticSolver,
}

__all__ = [
    "Solver",
    "BacktrackingSolver",
    "DancingLinksSolver",
    "CpSatSolver",
    "SatSolver",
    "GeneticSolver",
    "SOLVERS",
]
