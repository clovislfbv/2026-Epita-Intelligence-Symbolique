"""Sudoku grid model: parsing, formatting and validation.

A :class:`Grid` is an immutable 9x9 board. Cells hold values 1..9, with 0
representing an empty cell. Internally the board is stored as a flat tuple of
81 integers (row-major).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

N = 9
BOX = 3
CELLS = N * N
EMPTY = 0

# Characters that denote an empty cell when parsing string representations.
# Note: separator characters used by ``to_pretty`` (``-``, ``+``, ``|``) are
# intentionally NOT here, so a pretty-printed grid round-trips through parse().
_EMPTY_CHARS = {".", "_", "*"}


@dataclass(frozen=True)
class Grid:
    """An immutable 9x9 Sudoku grid stored as a flat tuple of 81 ints (0 = empty)."""

    cells: Tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.cells) != CELLS:
            raise ValueError(f"grid must have {CELLS} cells, got {len(self.cells)}")
        for v in self.cells:
            if not (0 <= v <= 9):
                raise ValueError(f"cell values must be in 0..9, got {v}")

    # ---- construction -----------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> "Grid":
        """Parse a grid from a string.

        Accepts the common 81-character form (``.`` / ``0`` for blanks) as well
        as multi-line / whitespace-formatted boards; any non-digit, non-empty
        marker character is ignored.
        """
        values: List[int] = []
        for ch in text:
            if ch.isdigit():
                values.append(int(ch))
            elif ch in _EMPTY_CHARS:
                values.append(EMPTY)
            # any other character (whitespace, separators) is skipped
        if len(values) != CELLS:
            raise ValueError(
                f"expected {CELLS} cells after parsing, got {len(values)}"
            )
        return cls(tuple(values))

    # ---- accessors --------------------------------------------------------
    def at(self, r: int, c: int) -> int:
        return self.cells[r * N + c]

    def rows(self) -> List[List[int]]:
        return [list(self.cells[r * N:(r + 1) * N]) for r in range(N)]

    def with_value(self, r: int, c: int, value: int) -> "Grid":
        idx = r * N + c
        new = list(self.cells)
        new[idx] = value
        return Grid(tuple(new))

    @property
    def num_clues(self) -> int:
        return sum(1 for v in self.cells if v != EMPTY)

    def is_complete(self) -> bool:
        return all(v != EMPTY for v in self.cells)

    # ---- validation -------------------------------------------------------
    def is_valid(self) -> bool:
        """True if no row, column or box contains a duplicate non-empty value."""
        return (
            self._units_ok(self._row_units())
            and self._units_ok(self._col_units())
            and self._units_ok(self._box_units())
        )

    def is_solved(self) -> bool:
        """True if the grid is complete and a valid Sudoku solution."""
        return self.is_complete() and self.is_valid()

    @staticmethod
    def _units_ok(units: Iterable[List[int]]) -> bool:
        for unit in units:
            seen = [v for v in unit if v != EMPTY]
            if len(seen) != len(set(seen)):
                return False
        return True

    def _row_units(self) -> List[List[int]]:
        return [list(self.cells[r * N:(r + 1) * N]) for r in range(N)]

    def _col_units(self) -> List[List[int]]:
        return [[self.cells[r * N + c] for r in range(N)] for c in range(N)]

    def _box_units(self) -> List[List[int]]:
        units = []
        for br in range(0, N, BOX):
            for bc in range(0, N, BOX):
                unit = [
                    self.cells[(br + dr) * N + (bc + dc)]
                    for dr in range(BOX)
                    for dc in range(BOX)
                ]
                units.append(unit)
        return units

    # ---- formatting -------------------------------------------------------
    def to_line(self, blank: str = ".") -> str:
        """One-line 81-character representation."""
        return "".join(str(v) if v != EMPTY else blank for v in self.cells)

    def to_pretty(self) -> str:
        """Human-readable boxed representation."""
        lines = []
        for r in range(N):
            if r % BOX == 0 and r != 0:
                lines.append("------+-------+------")
            parts = []
            for c in range(N):
                if c % BOX == 0 and c != 0:
                    parts.append("|")
                v = self.at(r, c)
                parts.append(str(v) if v != EMPTY else ".")
            lines.append(" ".join(parts))
        return "\n".join(lines)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.to_pretty()
