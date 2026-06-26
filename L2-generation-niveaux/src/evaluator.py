from __future__ import annotations

import math
from typing import Any, Dict

from .level import Level
from .tile import TileType, WALKABLE


class LevelEvaluator:

    def evaluate(self, level: Level) -> Dict[str, Any]:
        m: Dict[str, Any] = {}
        counts = level.tile_counts()
        total = level.width * level.height

        n_walkable = sum(counts[t] for t in WALKABLE)
        m["floor_density"] = n_walkable / total if total else 0.0

        comps = level.connected_components()
        if comps:
            largest = max(comps, key=len)
            m["connectivity_ratio"] = len(largest) / n_walkable if n_walkable else 0.0
            m["n_components"] = len(comps)
        else:
            m["connectivity_ratio"] = 0.0
            m["n_components"] = 0

        path = level.shortest_path()
        diagonal = math.sqrt(level.width ** 2 + level.height ** 2)
        if path is not None:
            m["path_exists"] = True
            m["path_length"] = len(path) - 1
            m["path_length_normalized"] = (len(path) - 1) / diagonal if diagonal else 0.0
        else:
            m["path_exists"] = False
            m["path_length"] = 0
            m["path_length_normalized"] = 0.0

        enemies = level.cells_of(TileType.ENEMY)
        m["enemy_count"] = len(enemies)
        m["item_count"]  = counts.get(TileType.ITEM, 0)
        m["trap_count"]  = counts.get(TileType.TRAP, 0)

        if level.start and enemies:
            dist_map = level.bfs_distances(level.start)
            edists = [dist_map.get(e, 0) for e in enemies]
            mean_d = sum(edists) / len(edists)
            m["enemy_mean_distance"] = mean_d
            m["enemy_distance_std"]  = math.sqrt(
                sum((d - mean_d) ** 2 for d in edists) / len(edists)
            )
            plen = m["path_length"]
            m["difficulty_gradient"] = mean_d / plen if plen else 0.0
        else:
            m["enemy_mean_distance"] = 0.0
            m["enemy_distance_std"]  = 0.0
            m["difficulty_gradient"] = 0.0

        tile_probs = [counts[t] / total for t in TileType if counts[t] > 0]
        m["tile_diversity"] = -sum(p * math.log2(p) for p in tile_probs if p > 0)

        m["symmetry_score"] = self._symmetry(level)
        m["quality_score"]  = self._quality(m)

        return m

    def _symmetry(self, level: Level) -> float:
        matches = total = 0
        for r in range(level.height):
            for c in range(level.width // 2):
                mc = level.width - 1 - c
                wl = level.at(r, c)  in WALKABLE
                wr = level.at(r, mc) in WALKABLE
                if wl == wr:
                    matches += 1
                total += 1
        return matches / total if total else 0.0

    def _quality(self, m: Dict[str, Any]) -> float:
        if not m.get("path_exists", False):
            return 0.0

        score = 0.0
        score += min(1.0, m["path_length_normalized"] / 0.30) * 0.30
        score += min(1.0, m["connectivity_ratio"] / 0.85) * 0.20

        d = m["floor_density"]
        if 0.20 <= d <= 0.50:
            ds = 1.0
        else:
            ds = max(0.0, 1.0 - abs(d - 0.35) / 0.35)
        score += ds * 0.15

        score += min(1.0, m["difficulty_gradient"] / 0.50) * 0.15
        score += min(1.0, m["tile_diversity"] / 2.0) * 0.10
        score += min(1.0, m["enemy_distance_std"] / 4.0) * 0.10

        return round(score, 4)

    def report(self, level: Level) -> str:
        m = self.evaluate(level)
        w = 52

        def bar(val: float, width: int = 20) -> str:
            n = round(val * width)
            return "[" + "#" * n + "·" * (width - n) + "]"

        lines = [
            "=" * w,
            f"  Evaluation -- {level.generator_name}  |  seed {level.seed}",
            f"  Grid: {level.width}x{level.height}",
            "=" * w,
            "",
            "PLAYABILITY",
            f"  Path exists          : {'YES' if m['path_exists'] else 'NO'}",
            f"  Path length          : {m['path_length']} steps  "
            f"(norm {m['path_length_normalized']:.2f})",
            f"  Connectivity         : {m['connectivity_ratio']:.1%}  "
            f"{bar(m['connectivity_ratio'])}",
            f"  Components           : {m['n_components']}",
            "",
            "DIFFICULTY",
            f"  Enemies              : {m['enemy_count']}",
            f"  Mean enemy distance  : {m['enemy_mean_distance']:.1f}  "
            f"(+/-{m['enemy_distance_std']:.1f})",
            f"  Difficulty gradient  : {m['difficulty_gradient']:.2f}  "
            f"{bar(min(1.0, m['difficulty_gradient']))}",
            f"  Items / Traps        : {m['item_count']} / {m['trap_count']}",
            "",
            "AESTHETICS",
            f"  Floor density        : {m['floor_density']:.1%}  "
            f"{bar(m['floor_density'])}",
            f"  Tile diversity       : {m['tile_diversity']:.2f} bits",
            f"  Symmetry score       : {m['symmetry_score']:.1%}  "
            f"{bar(m['symmetry_score'])}",
            "",
            f"  QUALITY SCORE        : {m['quality_score']:.3f} / 1.000  "
            f"{bar(m['quality_score'])}",
            "=" * w,
        ]
        return "\n".join(lines)
