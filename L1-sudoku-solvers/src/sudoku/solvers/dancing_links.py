"""Dancing Links (Knuth's Algorithm X) Sudoku solver.

Sudoku is modelled as an exact-cover problem with 324 columns (constraints):

* 81 cell constraints: each cell holds exactly one value
* 81 row constraints: each value appears once per row
* 81 column constraints: each value appears once per column
* 81 box constraints: each value appears once per box

Each candidate (row, col, value) is a matrix row covering exactly four columns.
Solved with the toroidal doubly-linked-list ("dancing links"). One node counted
per recursive call of Algorithm X.
"""

from __future__ import annotations

from typing import List, Optional

from ..board import EMPTY, N, Grid
from .base import Solver


class _Column:
    __slots__ = ("L", "R", "U", "D", "C", "size", "name", "row_id")

    def __init__(self, name=None, row_id=None):
        self.L = self.R = self.U = self.D = self
        self.C = self
        self.size = 0
        self.name = name
        self.row_id = row_id  # (r, c, v) for data nodes, None for headers


def _constraint_columns(r: int, c: int, v: int):
    """The four constraint-column indices covered by candidate (r, c, v)."""
    b = (r // 3) * 3 + (c // 3)
    return (
        r * 9 + c,            # cell
        81 + r * 9 + v,       # row-value
        162 + c * 9 + v,      # col-value
        243 + b * 9 + v,      # box-value
    )


class DancingLinksSolver(Solver):
    name = "dlx"
    supports_multi = True

    # ---- public ----------------------------------------------------------
    def _solve(self, grid: Grid):
        solutions = self._run(grid, limit=1)
        if not solutions:
            return None, self._nodes, None
        return solutions[0], self._nodes, None

    def solve_all(self, grid: Grid, limit: int = 2) -> List[Grid]:
        return self._run(grid, limit=limit)

    # ---- core ------------------------------------------------------------
    def _run(self, grid: Grid, limit: int) -> List[Grid]:
        self._nodes = 0
        header, _columns = self._build(grid)
        solution_rows: List = []
        results: List[Grid] = []
        self._search(header, solution_rows, results, limit)
        return results

    def _build(self, grid: Grid):
        header = _Column(name="root")
        columns = [_Column(name=i) for i in range(324)]
        prev = header
        for col in columns:
            col.L, col.R = prev, header
            prev.R = col
            header.L = col
            prev = col

        for r in range(N):
            for c in range(N):
                given = grid.at(r, c)
                vals = range(9) if given == EMPTY else [given - 1]
                for v in vals:
                    self._add_row(columns, r, c, v)
        return header, columns

    def _add_row(self, columns, r, c, v):
        cols = _constraint_columns(r, c, v)
        first = None
        for ci in cols:
            col = columns[ci]
            node = _Column(row_id=(r, c, v + 1))
            node.C = col
            # link vertically into the column
            node.D = col
            node.U = col.U
            col.U.D = node
            col.U = node
            col.size += 1
            # link horizontally into the row
            if first is None:
                first = node
                node.L = node.R = node
            else:
                node.L = first.L
                node.R = first
                first.L.R = node
                first.L = node

    @staticmethod
    def _cover(col: "_Column"):
        col.R.L = col.L
        col.L.R = col.R
        i = col.D
        while i is not col:
            j = i.R
            while j is not i:
                j.D.U = j.U
                j.U.D = j.D
                j.C.size -= 1
                j = j.R
            i = i.D

    @staticmethod
    def _uncover(col: "_Column"):
        i = col.U
        while i is not col:
            j = i.L
            while j is not i:
                j.C.size += 1
                j.D.U = j
                j.U.D = j
                j = j.L
            i = i.U
        col.R.L = col
        col.L.R = col

    def _choose_column(self, header):
        """Knuth's S heuristic: column with the fewest nodes."""
        best, best_size = None, None
        col = header.R
        while col is not header:
            if best_size is None or col.size < best_size:
                best, best_size = col, col.size
            col = col.R
        return best

    def _search(self, header, solution_rows, results, limit) -> bool:
        self._nodes += 1
        if header.R is header:
            results.append(self._to_grid(solution_rows))
            return len(results) >= limit
        col = self._choose_column(header)
        if col is None or col.size == 0:
            return False
        self._cover(col)
        r = col.D
        while r is not col:
            solution_rows.append(r)
            j = r.R
            while j is not r:
                self._cover(j.C)
                j = j.R
            if self._search(header, solution_rows, results, limit):
                return True
            solution_rows.pop()
            j = r.L
            while j is not r:
                self._uncover(j.C)
                j = j.L
            r = r.D
        self._uncover(col)
        return False

    @staticmethod
    def _to_grid(solution_rows) -> Grid:
        cells = [EMPTY] * 81
        for node in solution_rows:
            r, c, v = node.row_id
            cells[r * 9 + c] = v
        return Grid(tuple(cells))
