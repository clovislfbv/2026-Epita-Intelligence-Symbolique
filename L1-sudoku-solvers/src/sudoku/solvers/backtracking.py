"""Backtracking solver with MRV heuristic and forward checking.

Each cell keeps a bitmask of candidate values. We always branch on the unfilled
cell with the fewest candidates (Minimum-Remaining-Values), and forward-check by
pruning the chosen value from peers. A "node" is counted for every value
assignment attempt.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..board import EMPTY, N, Grid
from .base import Solver

FULL_MASK = 0b111111111  # candidates 1..9 as bits 0..8


def _peers() -> List[List[int]]:
    """Precompute, for each of the 81 cells, the indices of its 20 peers."""
    peers: List[List[int]] = []
    for idx in range(81):
        r, c = divmod(idx, N)
        s = set()
        for cc in range(N):
            s.add(r * N + cc)
        for rr in range(N):
            s.add(rr * N + c)
        br, bc = (r // 3) * 3, (c // 3) * 3
        for dr in range(3):
            for dc in range(3):
                s.add((br + dr) * N + (bc + dc))
        s.discard(idx)
        peers.append(sorted(s))
    return peers


_PEERS = _peers()


class BacktrackingSolver(Solver):
    name = "backtracking"

    def _solve(self, grid: Grid):
        # candidates[idx] = bitmask of allowed values for empty cells.
        values = list(grid.cells)
        cand = [FULL_MASK] * 81
        nodes = [0]

        # Initialise candidates from the given clues via constraint propagation.
        # Clue assignments are never undone, so their trail is discarded.
        for idx, v in enumerate(values):
            if v != EMPTY:
                if not self._assign(values, cand, idx, v, []):
                    return None, nodes[0], None  # contradictory puzzle

        solved = self._search(values, cand, nodes)
        if not solved:
            return None, nodes[0], None
        return Grid(tuple(values)), nodes[0], None

    def _assign(self, values, cand, idx, v, trail) -> bool:
        """Place value ``v`` at ``idx`` and forward-check peers.

        Every mutation is recorded onto ``trail`` (a list of ``(cell, value,
        mask)`` triples) so it can be reverted incrementally by :meth:`_undo`,
        avoiding a full copy of the two 81-element arrays at each branch.
        Returns False on conflict (a peer left with no candidate).
        """
        bit = 1 << (v - 1)
        if not (cand[idx] & bit):
            return False  # value already eliminated here (e.g. conflicting clues)
        trail.append((idx, values[idx], cand[idx]))
        values[idx] = v
        cand[idx] = bit
        for p in _PEERS[idx]:
            if values[p] == v:
                return False  # a peer already holds this value (conflicting clues)
            if values[p] == EMPTY and (cand[p] & bit):
                trail.append((p, values[p], cand[p]))
                cand[p] &= ~bit
                if cand[p] == 0:
                    return False
        return True

    @staticmethod
    def _undo(values, cand, trail) -> None:
        """Revert every mutation recorded on ``trail`` (in reverse order)."""
        for idx, value, mask in reversed(trail):
            values[idx] = value
            cand[idx] = mask

    def _select(self, values, cand) -> int:
        """Return the empty cell index with fewest candidates (MRV), or -1."""
        best, best_count = -1, 10
        for idx in range(81):
            if values[idx] == EMPTY:
                count = bin(cand[idx]).count("1")
                if count < best_count:
                    best, best_count = idx, count
                    if count == 1:
                        break
        return best

    def _search(self, values, cand, nodes) -> bool:
        idx = self._select(values, cand)
        if idx == -1:
            return True  # no empty cell left -> solved
        mask = cand[idx]
        for v in range(1, 10):
            if mask & (1 << (v - 1)):
                nodes[0] += 1
                trail: List[Tuple[int, int, int]] = []
                if self._assign(values, cand, idx, v, trail) and self._search(values, cand, nodes):
                    return True
                self._undo(values, cand, trail)
        return False
