from __future__ import annotations

import math
import random
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from .level import Level
from .tile import WALKABLE, WEIGHTS, WFC_RULES, TileType

_DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]
STRUCTURAL = [TileType.VOID, TileType.WALL, TileType.FLOOR]


class WFCGenerator:

    def __init__(
        self,
        width: int = 30,
        height: int = 20,
        seed: Optional[int] = None,
        *,
        floor_density_target: float = 0.35,
        enemy_density: float = 0.05,
        item_density: float = 0.03,
        trap_density: float = 0.015,
        symmetry: bool = False,
    ):
        self.width = width
        self.height = height
        self.seed = seed
        self.rng = random.Random(seed)
        self.floor_density_target = floor_density_target
        self.enemy_density = enemy_density
        self.item_density = item_density
        self.trap_density = trap_density
        self.symmetry = symmetry
        self._sup: List[List[Set[TileType]]] = []
        self._col: List[List[Optional[TileType]]] = []

    def _init(self):
        all_tiles = set(STRUCTURAL)
        self._sup = [[set(all_tiles) for _ in range(self.width)]
                     for _ in range(self.height)]
        self._col = [[None] * self.width for _ in range(self.height)]

    def _force(self, r: int, c: int, tile: TileType):
        self._sup[r][c] = {tile}
        self._col[r][c] = tile

    def _entropy(self, r: int, c: int) -> float:
        poss = self._sup[r][c]
        if not poss:
            return -1.0
        total = sum(WEIGHTS[t] for t in poss)
        if total == 0:
            return 0.0
        h = -sum((WEIGHTS[t] / total) * math.log(WEIGHTS[t] / total)
                 for t in poss if WEIGHTS[t] > 0)
        return h + self.rng.uniform(0.0, 1e-5)

    def _propagate(self, seeds: List[Tuple[int, int]]) -> bool:
        q: deque = deque(seeds)
        in_q: Set[Tuple[int, int]] = set(seeds)
        while q:
            r, c = q.popleft()
            in_q.discard((r, c))
            cur = self._sup[r][c]
            for d, (dr, dc) in enumerate(_DIRS):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < self.height and 0 <= nc < self.width):
                    continue
                if self._col[nr][nc] is not None:
                    continue
                allowed: Set[TileType] = set()
                for tile in cur:
                    allowed |= WFC_RULES[tile][d]
                new_poss = self._sup[nr][nc] & allowed
                if len(new_poss) < len(self._sup[nr][nc]):
                    if not new_poss:
                        return False
                    self._sup[nr][nc] = new_poss
                    if len(new_poss) == 1:
                        self._col[nr][nc] = next(iter(new_poss))
                    if (nr, nc) not in in_q:
                        q.append((nr, nc))
                        in_q.add((nr, nc))
        return True

    def _run_wfc(self) -> bool:
        while True:
            best_e = float("inf")
            best_cell: Optional[Tuple[int, int]] = None
            for r in range(self.height):
                for c in range(self.width):
                    if self._col[r][c] is not None:
                        continue
                    e = self._entropy(r, c)
                    if e < 0:
                        return False
                    if e < best_e:
                        best_e = e
                        best_cell = (r, c)
            if best_cell is None:
                return True
            r, c = best_cell
            poss = list(self._sup[r][c])
            weights = [WEIGHTS[t] for t in poss]
            tile = self.rng.choices(poss, weights=weights,k=1)[0]
            self._force(r, c, tile)
            if not self._propagate([(r, c)]):
                return False

    def _components(self, grid: List[List[TileType]]) -> List[Set[Tuple[int, int]]]:
        visited: Set[Tuple[int, int]] = set()
        result: List[Set[Tuple[int, int]]] = []
        for r in range(self.height):
            for c in range(self.width):
                if grid[r][c] in WALKABLE and (r, c) not in visited:
                    comp: Set[Tuple[int, int]] = set()
                    q: deque = deque([(r, c)])
                    while q:
                        cr, cc = q.popleft()
                        if (cr, cc) in visited:
                            continue
                        visited.add((cr, cc))
                        comp.add((cr, cc))
                        for dr, dc in _DIRS:
                            nb = (cr + dr, cc + dc)
                            if (0 <= nb[0] < self.height and
                                    0 <= nb[1] < self.width and
                                    grid[nb[0]][nb[1]] in WALKABLE and
                                    nb not in visited):
                                q.append(nb)
                    result.append(comp)
        return result

    def _bfs_dist(
        self, grid: List[List[TileType]], start: Tuple[int, int]
    ) -> Dict[Tuple[int, int], int]:
        dist = {start: 0}
        q: deque = deque([start])
        while q:
            r, c = q.popleft()
            for dr, dc in _DIRS:
                nb = (r + dr, c + dc)
                if (nb not in dist and
                        0 <= nb[0] < self.height and
                        0 <= nb[1] < self.width and
                        grid[nb[0]][nb[1]] in WALKABLE):
                    dist[nb] = dist[(r,c)] + 1
                    q.append(nb)
        return dist

    def _connect_components(self, grid: List[List[TileType]]) -> List[List[TileType]]:
        comps = self._components(grid)
        if len(comps) <= 1:
            return grid
        comps.sort(key=len, reverse=True)
        main = comps[0]
        for comp in comps[1:]:
            if len(comp) < 2:
                continue
            main_s = list(main)[: min(60, len(main))]
            comp_s = list(comp)[: min(20, len(comp))]
            best_d = float("inf")
            p1 = p2 = (0, 0)
            for a in main_s:
                for b in comp_s:
                    d = abs(a[0] - b[0]) + abs(a[1] - b[1])
                    if d < best_d:
                        best_d, p1, p2 = d, a, b
            r, c = p1
            while r != p2[0]:
                grid[r][c] = TileType.FLOOR
                main.add((r, c))
                r += 1 if r < p2[0] else -1
            while c != p2[1]:
                grid[r][c] = TileType.FLOOR
                main.add((r, c))
                c += 1 if c < p2[1] else -1
            main |= comp
        return grid

    def _apply_symmetry(self, grid: List[List[TileType]]) -> List[List[TileType]]:
        mid = self.width // 2
        for r in range(self.height):
            for c in range(mid):
                grid[r][self.width - 1 - c] = grid[r][c]
        return grid

    def _room_fallback(self) -> List[List[TileType]]:
        grid = [[TileType.WALL] * self.width for _ in range(self.height)]
        rooms: List[Tuple[int, int, int, int]] = []
        target = max(4, (self.width * self.height) // 70)

        for _ in range(target * 10):
            if len(rooms) >= target:
                break
            rw = self.rng.randint(4, min(10, self.width // 3))
            rh = self.rng.randint(3, min(7, self.height // 3))
            rx = self.rng.randint(1, self.width - rw - 1)
            ry = self.rng.randint(1, self.height - rh - 1)
            if any(
                not (rx + rw + 1 < ex or ex + ew + 1 < rx or
                     ry + rh + 1 < ey or ey + eh + 1 < ry)
                for ex, ey, ew, eh in rooms
            ):
                continue
            rooms.append((rx, ry, rw, rh))
            for rr in range(ry, ry + rh):
                for cc in range(rx, rx + rw):
                    grid[rr][cc] = TileType.FLOOR

        for i in range(len(rooms) - 1):
            x1 = rooms[i][0] + rooms[i][2] // 2
            y1 = rooms[i][1] + rooms[i][3] // 2
            x2 = rooms[i+1][0] + rooms[i+1][2] // 2
            y2 = rooms[i+1][1] + rooms[i+1][3] // 2
            cx, cy = x1, y1
            while cx != x2:
                grid[cy][cx] = TileType.FLOOR
                cx += 1 if cx < x2 else -1
            while cy != y2:
                grid[cy][cx] = TileType.FLOOR
                cy += 1 if cy < y2 else -1

        if self.symmetry:
            self._apply_symmetry(grid)
        return grid

    def _place_elements(self, grid: List[List[TileType]]) -> List[List[TileType]]:
        comps = self._components(grid)
        if not comps:
            return grid
        main = max(comps, key=len)
        cells = list(main)
        if len(cells) < 4:
            return grid

        start = self.rng.choice(cells)
        dist = self._bfs_dist(grid, start)
        reachable = sorted([c for c in cells if c in dist], key=lambda c: dist[c])
        end = reachable[-1]
        max_d = dist[end]

        grid[start[0]][start[1]] = TileType.START
        grid[end[0]][end[1]] = TileType.END

        used = {start, end}
        pool = [c for c in reachable if c not in used]

        def _place(tile: TileType, density: float,
                   min_frac: float = 0.0, max_frac: float = 1.0):
            n = max(0, int(len(cells) * density))
            candidates = [c for c in pool
                          if c not in used and
                          min_frac * max_d <= dist.get(c, 0) <= max_frac * max_d]
            self.rng.shuffle(candidates)
            for cell in candidates[:n]:
                grid[cell[0]][cell[1]] = tile
                used.add(cell)

        _place(TileType.ENEMY, self.enemy_density, 0.30, 1.00)
        _place(TileType.ITEM,  self.item_density,  0.00, 0.60)
        _place(TileType.TRAP,  self.trap_density,  0.40, 1.00)

        return grid

    def _generate_structure(self, max_attempts: int = 20) -> List[List[TileType]]:
        min_floor = max(8, int(self.width * self.height * self.floor_density_target * 0.4))

        for attempt in range(max_attempts):
            self._init()

            borders = []
            for r in range(self.height):
                for c in range(self.width):
                    if (r == 0 or r == self.height - 1 or
                            c == 0 or c == self.width - 1):
                        self._force(r, c, TileType.WALL)
                        borders.append((r, c))
            if not self._propagate(borders):
                continue

            if attempt < 8:
                cr, cc = self.height // 2, self.width // 2
                self._force(cr, cc, TileType.FLOOR)
                if not self._propagate([(cr, cc)]):
                    continue

            if not self._run_wfc():
                continue

            grid = [list(row) for row in self._col]

            if self.symmetry:
                self._apply_symmetry(grid)

            floor_count = sum(
                1 for r in range(self.height)
                for c in range(self.width)
                if grid[r][c] == TileType.FLOOR
            )
            if floor_count >= min_floor:
                return grid

        return self._room_fallback()

    def generate(self) -> Level:
        grid = self._generate_structure()
        grid = self._connect_components(grid)
        grid = self._place_elements(grid)
        return Level(
            grid=grid,
            seed=self.seed,
            generator_name="WFC",
            params={
                "width": self.width,
                "height": self.height,
                "floor_density_target": self.floor_density_target,
                "enemy_density": self.enemy_density,
                "item_density": self.item_density,
                "trap_density": self.trap_density,
                "symmetry": self.symmetry,
            },
        )
