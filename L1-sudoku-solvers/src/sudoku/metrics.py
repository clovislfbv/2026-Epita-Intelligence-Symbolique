"""Result and metric types shared by every solver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .board import Grid


@dataclass
class SolveResult:
    """Outcome and performance metrics of a single solve attempt.

    Attributes
    ----------
    solver:
        Name of the solver that produced this result.
    solved:
        Whether a valid complete solution was found.
    solution:
        The solved grid, or ``None`` if unsolved / timed out.
    elapsed_s:
        Wall-clock solve time in seconds.
    nodes:
        Number of search nodes explored. ``None`` when the paradigm does not
        expose a comparable counter.
    peak_mem_bytes:
        Peak memory measured via ``tracemalloc`` during the solve, or ``None``.
    extra:
        Solver-specific extra stats (e.g. SAT conflicts, GA generations).
    timed_out:
        Whether the run was aborted by the benchmark timeout.
    """

    solver: str
    solved: bool
    solution: Optional[Grid] = None
    elapsed_s: float = 0.0
    nodes: Optional[int] = None
    peak_mem_bytes: Optional[int] = None
    timed_out: bool = False
    extra: dict = field(default_factory=dict)
