from __future__ import annotations

import random
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from .level import Level
from .tile import TileType, WALKABLE

try:
    from ortools.sat.python import cp_model as _cp_model
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

_DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]


class CPSATGenerator:

    def __init__(
        self,
        width: int = 25,
        height: int = 16,
        seed: Optional[int] = None,
        *,
        min_floor_ratio: float = 0.18,
        max_floor_ratio: float = 0.48,
        enemy_density: float = 0.05,
        item_density: float = 0.03,
        trap_density: float = 0.015,
        symmetry: bool = False,
        timeout_seconds: float = 30.0,
    ):
        self.width = width
        self.height = height
        self.seed = seed
        self.rng = random.Random(seed)
        self.min_floor_ratio = min_floor_ratio
        self.max_floor_ratio = max_floor_ratio
        self.enemy_density = enemy_density
        self.item_density = item_density
        self.trap_density = trap_density
        self.symmetry = symmetry
        self.timeout_seconds = timeout_seconds

    def _build_and_solve(self):
        if not HAS_ORTOOLS:
            return None

        cp = _cp_model.CpModel()
        H, W = self.height, self.width

        void_v  = [[cp.NewBoolVar(f"v_{r}_{c}") for c in range(W)] for r in range(H)]
        wall_v  = [[cp.NewBoolVar(f"w_{r}_{c}") for c in range(W)] for r in range(H)]
        floor_v = [[cp.NewBoolVar(f"f_{r}_{c}") for c in range(W)] for r in range(H)]

        for r in range(H):
            for c in range(W):
                cp.AddExactlyOne([void_v[r][c], wall_v[r][c], floor_v[r][c]])

        for r in range(H):
            cp.Add(wall_v[r][0]   == 1)
            cp.Add(wall_v[r][W-1] == 1)
        for c in range(W):
            cp.Add(wall_v[0][c]   == 1)
            cp.Add(wall_v[H-1][c] == 1)

        for r in range(H):
            for c in range(W):
                for dr, dc in _DIRS:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < H and 0 <= nc < W:
                        cp.AddImplication(void_v[r][c],  floor_v[nr][nc].Not())
                        cp.AddImplication(floor_v[r][c], void_v[nr][nc].Not())

        for r in range(1, H-1):
            for c in range(1, W-1):
                nb_floor = [
                    floor_v[r+dr][c+dc]
                    for dr, dc in _DIRS
                    if 0 <= r+dr < H and 0 <= c+dc < W
                ]
                if nb_floor:
                    cp.Add(sum(nb_floor) >= 1).OnlyEnforceIf(floor_v[r][c])

        total = H * W
        all_floor = [floor_v[r][c] for r in range(H) for c in range(W)]
        cp.Add(sum(all_floor) >= max(6, int(total * self.min_floor_ratio)))
        cp.Add(sum(all_floor) <= int(total * self.max_floor_ratio))

        if self.symmetry:
            mid = W // 2
            for r in range(H):
                for c in range(mid):
                    mc = W - 1 - c
                    cp.Add(void_v[r][c]  == void_v[r][mc])
                    cp.Add(wall_v[r][c]  == wall_v[r][mc])
                    cp.Add(floor_v[r][c] == floor_v[r][mc])

        for r in range(1, H-1):
            for c in range(1, W-1):
                dist_norm = (abs(r - H//2) + abs(c - W//2)) / ((H + W) / 2)
                use_floor = self.rng.random() < (0.45 - dist_norm * 0.25)
                if use_floor:
                    cp.AddHint(floor_v[r][c], 1)
                    cp.AddHint(wall_v[r][c],  0)
                    cp.AddHint(void_v[r][c],  0)
                else:
                    cp.AddHint(floor_v[r][c], 0)
                    cp.AddHint(wall_v[r][c],  1)
                    cp.AddHint(void_v[r][c],  0)

        solver = _cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.timeout_seconds
        solver.parameters.random_seed = (self.seed or 0) % (2**31)
        solver.parameters.num_search_workers = 1

        status = solver.Solve(cp)

        if status not in (_cp_model.OPTIMAL, _cp_model.FEASIBLE):
            return None

        grid: List[List[TileType]] = []
        for r in range(H):
            row = []
            for c in range(W):
                if solver.Value(floor_v[r][c]):
                    row.append(TileType.FLOOR)
                elif solver.Value(wall_v[r][c]):
                    row.append(TileType.WALL)
                else:
                    row.append(TileType.VOID)
            grid.append(row)

        return grid

    def _connect_components(self, grid) -> None:
        H, W = len(grid), len(grid[0])
        visited: Set[Tuple[int, int]] = set()
        comps: List[Set[Tuple[int, int]]] = []
        for r in range(H):
            for c in range(W):
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
                            nb = (cr+dr, cc+dc)
                            if (0 <= nb[0] < H and 0 <= nb[1] < W and
                                    grid[nb[0]][nb[1]] in WALKABLE and
                                    nb not in visited):
                                q.append(nb)
                    comps.append(comp)
        if len(comps) <= 1:
            return
        comps.sort(key=len, reverse=True)
        main = comps[0]
        for comp in comps[1:]:
            if len(comp) < 2:
                continue
            ms = list(main)[:min(60, len(main))]
            cs = list(comp)[:min(20, len(comp))]
            best_d = float("inf")
            p1 = p2 = (0, 0)
            for a in ms:
                for b in cs:
                    d = abs(a[0]-b[0]) + abs(a[1]-b[1])
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

    def _largest_component(self, grid) -> Set[Tuple[int, int]]:
        H, W = len(grid), len(grid[0])
        visited: Set[Tuple[int, int]] = set()
        best: Set[Tuple[int, int]] = set()
        for r in range(H):
            for c in range(W):
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
                            nb = (cr+dr, cc+dc)
                            if (0 <= nb[0] < H and 0 <= nb[1] < W and
                                    grid[nb[0]][nb[1]] in WALKABLE and
                                    nb not in visited):
                                q.append(nb)
                    if len(comp) > len(best):
                        best = comp
        return best

    def _bfs_dist(self, grid, start) -> Dict[Tuple[int, int], int]:
        H, W = len(grid), len(grid[0])
        dist = {start: 0}
        q: deque = deque([start])
        while q:
            r, c = q.popleft()
            for dr, dc in _DIRS:
                nb = (r+dr, c+dc)
                if (nb not in dist and 0 <= nb[0] < H and 0 <= nb[1] < W and
                        grid[nb[0]][nb[1]] in WALKABLE):
                    dist[nb] = dist[(r,c)] + 1
                    q.append(nb)
        return dist

    def _place_elements(self, grid):
        main = self._largest_component(grid)
        if len(main) < 4:
            return grid
        cells = list(main)
        start = self.rng.choice(cells)
        dist = self._bfs_dist(grid, start)
        reachable = sorted([c for c in cells if c in dist], key=lambda c: dist[c])
        end = reachable[-1]
        max_d = dist[end]

        grid[start[0]][start[1]] = TileType.START
        grid[end[0]][end[1]]     = TileType.END
        used = {start, end}

        def _place(tile: TileType, density: float, lo: float, hi: float):
            n = max(0, int(len(cells) * density))
            cands = [c for c in reachable if c not in used and
                     lo * max_d <= dist.get(c, 0) <= hi * max_d]
            self.rng.shuffle(cands)
            for cell in cands[:n]:
                grid[cell[0]][cell[1]] = tile
                used.add(cell)

        _place(TileType.ENEMY, self.enemy_density, 0.30, 1.00)
        _place(TileType.ITEM,  self.item_density,  0.00, 0.60)
        _place(TileType.TRAP,  self.trap_density,  0.40, 1.00)
        return grid

    def generate(self) -> Level:
        grid = self._build_and_solve()

        if grid is None:
            from .wfc import WFCGenerator
            fallback = WFCGenerator(self.width, self.height, seed=self.seed,
                                    symmetry=self.symmetry)
            fallback_level = fallback.generate()
            return Level(
                grid=fallback_level.grid,
                seed=self.seed,
                generator_name="CP-SAT(fallback->WFC)",
                params=fallback_level.params,
            )

        self._connect_components(grid)
        grid = self._place_elements(grid)
        return Level(
            grid=grid,
            seed=self.seed,
            generator_name="CP-SAT",
            params={
                "width": self.width,
                "height": self.height,
                "min_floor_ratio": self.min_floor_ratio,
                "max_floor_ratio": self.max_floor_ratio,
                "symmetry": self.symmetry,
            },
        )
