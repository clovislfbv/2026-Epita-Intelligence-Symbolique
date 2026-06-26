from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from .tile import TileType, WALKABLE


class Level:
    DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]

    def __init__(
        self,
        grid: List[List[TileType]],
        seed: Optional[int] = None,
        generator_name: str = "unknown",
        params: Optional[dict] = None,
    ):
        self.grid = grid
        self.height = len(grid)
        self.width = len(grid[0]) if grid else 0
        self.seed = seed
        self.generator_name = generator_name
        self.params = params or {}

    def at(self, r: int, c: int) -> TileType:
        if 0 <= r < self.height and 0 <= c < self.width:
            return self.grid[r][c]
        return TileType.VOID

    @property
    def start(self) -> Optional[Tuple[int, int]]:
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c] == TileType.START:
                    return (r, c)
        return None

    @property
    def end(self) -> Optional[Tuple[int, int]]:
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c] == TileType.END:
                    return (r, c)
        return None

    def cells_of(self, tile: TileType) -> List[Tuple[int, int]]:
        return [
            (r, c)
            for r in range(self.height)
            for c in range(self.width)
            if self.grid[r][c] == tile
        ]

    def walkable_cells(self) -> List[Tuple[int, int]]:
        return [
            (r, c)
            for r in range(self.height)
            for c in range(self.width)
            if self.grid[r][c] in WALKABLE
        ]

    def tile_counts(self) -> Dict[TileType, int]:
        counts: Dict[TileType, int] = {t: 0 for t in TileType}
        for row in self.grid:
            for tile in row:
                counts[tile] += 1
        return counts

    def bfs_distances(self, start: Tuple[int, int]) -> Dict[Tuple[int, int], int]:
        if self.at(*start) not in WALKABLE:
            return {}
        dist: Dict[Tuple[int, int], int] = {start: 0}
        q: deque = deque([start])
        while q:
            r, c = q.popleft()
            for dr, dc in self.DIRS:
                nb = (r + dr, c + dc)
                if (
                    nb not in dist
                    and 0 <= nb[0] < self.height
                    and 0 <= nb[1] < self.width
                    and self.grid[nb[0]][nb[1]] in WALKABLE
                ):
                    dist[nb] = dist[(r, c)] + 1
                    q.append(nb)
        return dist

    def shortest_path(
        self,
        start: Optional[Tuple[int, int]] = None,
        end: Optional[Tuple[int, int]] = None,
    ) -> Optional[List[Tuple[int, int]]]:
        src = start or self.start
        dst = end or self.end
        if src is None or dst is None:
            return None

        parent: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {src: None}
        q: deque = deque([src])
        while q:
            r, c = q.popleft()
            if (r, c) == dst:
                path: List[Tuple[int, int]] = []
                node: Optional[Tuple[int, int]] = dst
                while node is not None:
                    path.append(node)
                    node = parent[node]
                path.reverse()
                return path
            for dr, dc in self.DIRS:
                nb = (r + dr, c + dc)
                if (
                    nb not in parent
                    and 0 <= nb[0] < self.height
                    and 0 <= nb[1] < self.width
                    and self.grid[nb[0]][nb[1]] in WALKABLE
                ):
                    parent[nb] = (r, c)
                    q.append(nb)
        return None

    def connected_components(self) -> List[Set[Tuple[int, int]]]:
        visited: Set[Tuple[int, int]] = set()
        components: List[Set[Tuple[int, int]]] = []
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c] in WALKABLE and (r, c) not in visited:
                    comp: Set[Tuple[int, int]] = set()
                    q: deque = deque([(r, c)])
                    while q:
                        cr, cc = q.popleft()
                        if (cr, cc) in visited:
                            continue
                        visited.add((cr, cc))
                        comp.add((cr, cc))
                        for dr, dc in self.DIRS:
                            nb = (cr + dr, cc + dc)
                            if (
                                0 <= nb[0] < self.height
                                and 0 <= nb[1] < self.width
                                and self.grid[nb[0]][nb[1]] in WALKABLE
                                and nb not in visited
                            ):
                                q.append(nb)
                    components.append(comp)
        return components
