"""Instance loading and difficulty-bucketed puzzle generation.

Loads the curated set from ``data/instances.json`` (one puzzle per record,
tagged with a difficulty bucket). Can also generate puzzles by digging holes out
of a full solution, using a solution-counting solver to control uniqueness.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .board import EMPTY, N, Grid

_DATA = Path(__file__).resolve().parents[2] / "data" / "instances.json"

# Bucket display order, easiest first.
BUCKET_ORDER = ["easy", "medium", "hard", "very_hard", "minimal-17", "multi"]

# Target number of holes (empty cells) per difficulty bucket for generation.
# More holes -> fewer clues -> harder. Digging stops early if removing a cell
# would break uniqueness, so the realised count can be slightly lower.
BUCKET_HOLES = {
    "easy": 40,
    "medium": 46,
    "hard": 50,
    "very_hard": 54,
    "minimal-17": 64,
}


@dataclass
class Instance:
    id: str
    bucket: str
    grid: Grid
    note: str = ""
    expected_solutions: int = 1


def load_instances(path: Optional[Path] = None) -> List[Instance]:
    """Load the curated benchmark instances from JSON."""
    path = path or _DATA
    data = json.loads(Path(path).read_text())
    instances = []
    for rec in data["instances"]:
        instances.append(
            Instance(
                id=rec["id"],
                bucket=rec["bucket"],
                grid=Grid.parse(rec["puzzle"]),
                note=rec.get("note", ""),
                expected_solutions=rec.get("expected_solutions", 1),
            )
        )
    return _sorted(instances)


def _sorted(instances: List[Instance]) -> List[Instance]:
    def key(i: Instance):
        b = i.bucket
        return (BUCKET_ORDER.index(b) if b in BUCKET_ORDER else len(BUCKET_ORDER), i.id)

    return sorted(instances, key=key)


def filter_buckets(instances: List[Instance], buckets: Optional[List[str]]) -> List[Instance]:
    if not buckets or "all" in buckets:
        return instances
    wanted = set(buckets)
    return [i for i in instances if i.bucket in wanted]


# ---- generation ----------------------------------------------------------
def random_full_solution(seed: Optional[int] = None) -> Grid:
    """Produce a random complete, valid Sudoku grid via randomized backtracking."""
    rng = random.Random(seed)
    cells = [EMPTY] * 81

    def candidates(idx: int) -> List[int]:
        r, c = divmod(idx, N)
        used = set()
        for cc in range(N):
            used.add(cells[r * N + cc])
        for rr in range(N):
            used.add(cells[rr * N + c])
        br, bc = (r // 3) * 3, (c // 3) * 3
        for dr in range(3):
            for dc in range(3):
                used.add(cells[(br + dr) * N + (bc + dc)])
        opts = [v for v in range(1, 10) if v not in used]
        rng.shuffle(opts)
        return opts

    def fill(idx: int) -> bool:
        if idx == 81:
            return True
        for v in candidates(idx):
            cells[idx] = v
            if fill(idx + 1):
                return True
            cells[idx] = EMPTY
        return False

    fill(0)
    return Grid(tuple(cells))


def make_unique_puzzle(
    holes: int = 50, seed: Optional[int] = None, counter=None
) -> Grid:
    """Dig ``holes`` cells out of a random solution while keeping a unique solution.

    ``counter`` is a callable ``grid -> number_of_solutions(up to 2)``; defaults
    to a Dancing Links count. Cells are only removed if the puzzle still has a
    single solution.
    """
    if counter is None:
        from .solvers.dancing_links import DancingLinksSolver

        solver = DancingLinksSolver()
        counter = lambda g: len(solver.solve_all(g, limit=2))  # noqa: E731

    rng = random.Random(seed)
    full = random_full_solution(seed)
    cells = list(full.cells)
    order = list(range(81))
    rng.shuffle(order)
    removed = 0
    for idx in order:
        if removed >= holes:
            break
        saved = cells[idx]
        cells[idx] = EMPTY
        if counter(Grid(tuple(cells))) == 1:
            removed += 1
        else:
            cells[idx] = saved  # restore: removal broke uniqueness
    return Grid(tuple(cells))


def count_solutions(grid: Grid, limit: int = 2) -> int:
    """Count solutions of ``grid``, capped at ``limit`` (via Dancing Links)."""
    from .solvers.dancing_links import DancingLinksSolver

    return len(DancingLinksSolver().solve_all(grid, limit=limit))


def generate_puzzle(
    bucket: str = "medium", seed: Optional[int] = None, holes: Optional[int] = None
) -> Grid:
    """Generate one puzzle for a difficulty ``bucket``.

    ``multi`` yields a non-unique puzzle (for enumeration); every other bucket
    yields a uniquely-solvable puzzle dug to ``holes`` empty cells (defaulting to
    :data:`BUCKET_HOLES` for the bucket, or 50 if unknown).
    """
    if bucket == "multi":
        return make_multi_solution_puzzle(seed)
    if holes is None:
        holes = BUCKET_HOLES.get(bucket, 50)
    return make_unique_puzzle(holes=holes, seed=seed)


def make_multi_solution_puzzle(seed: Optional[int] = None) -> Grid:
    """Return a puzzle with at least two solutions (for enumeration tests).

    We dig holes out of a random solution one at a time and stop as soon as the
    puzzle admits more than one solution.
    """
    from .solvers.dancing_links import DancingLinksSolver

    solver = DancingLinksSolver()
    rng = random.Random(seed)
    full = random_full_solution(seed)
    cells = list(full.cells)
    order = list(range(81))
    rng.shuffle(order)
    for idx in order:
        cells[idx] = EMPTY
        if len(solver.solve_all(Grid(tuple(cells)), limit=2)) >= 2:
            break
    return Grid(tuple(cells))
