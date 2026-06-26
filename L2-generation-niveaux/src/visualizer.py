from __future__ import annotations

from typing import List, Set, Tuple

from .level import Level
from .tile import COLORS, RESET, SYMBOLS, TileType, WALKABLE


class LevelVisualizer:

    def __init__(self, use_color: bool = True):
        self.use_color = use_color

    def render(
        self,
        level: Level,
        highlight_path: bool = True,
        show_distances: bool = False,
    ) -> str:
        path_cells: Set[Tuple[int, int]] = set()
        dist_map = {}

        if highlight_path:
            path = level.shortest_path()
            if path:
                path_cells = set(path)

        if show_distances and level.start:
            dist_map = level.bfs_distances(level.start)

        top    = "╔" + "══" * level.width + "╗"
        bottom = "╚" + "══" * level.width + "╝"
        rows = [top]

        for r in range(level.height):
            line = "║"
            for c in range(level.width):
                tile = level.at(r, c)
                sym  = SYMBOLS[tile]

                if (r, c) in path_cells and tile not in {TileType.START, TileType.END}:
                    cell = ("\033[96m·" + RESET) if self.use_color else "·"
                elif show_distances and (r, c) in dist_map and tile == TileType.FLOOR:
                    d = dist_map[(r, c)]
                    dsym = str(d % 10)
                    if self.use_color:
                        colours = ["\033[92m", "\033[93m", "\033[91m"]
                        col = colours[min(2, d * 3 // max(max(dist_map.values()), 1))]
                        cell = col + dsym + RESET
                    else:
                        cell = dsym
                else:
                    cell = (COLORS[tile] + sym + RESET) if self.use_color else sym

                line += cell + " "
            line += "║"
            rows.append(line)

        rows.append(bottom)
        return "\n".join(rows)

    def legend(self) -> str:
        parts = []
        for tile in TileType:
            sym = SYMBOLS[tile]
            if self.use_color:
                sym = COLORS[tile] + sym + RESET
            parts.append(f"{sym}={tile.name}")
        return "  " + "  ".join(parts)

    def print_level(
        self,
        level: Level,
        title: str = "",
        show_path: bool = True,
        show_distances: bool = False,
    ):
        if title:
            w = max(50, len(title) + 4)
            print("\n" + "-" * w)
            print(f"  {title}")
            print("-" * w)
        print(self.render(level, highlight_path=show_path,
                          show_distances=show_distances))
        print(self.legend())

    def plot(
        self,
        level: Level,
        title: str = "",
        show_path: bool = True,
        save: bool = True,
    ) -> None:
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
            import numpy as np
        except ImportError:
            print("[visualizer] matplotlib not available")
            return

        rgb: dict = {
            TileType.VOID:  [0.08, 0.08, 0.08],
            TileType.WALL:  [0.42, 0.42, 0.42],
            TileType.FLOOR: [0.92, 0.88, 0.76],
            TileType.START: [0.10, 0.85, 0.10],
            TileType.END:   [0.90, 0.10, 0.10],
            TileType.ENEMY: [0.85, 0.20, 0.20],
            TileType.ITEM:  [0.95, 0.85, 0.05],
            TileType.TRAP:  [0.70, 0.10, 0.70],
        }
        img = np.array(
            [[rgb[level.at(r, c)] for c in range(level.width)]
             for r in range(level.height)],
            dtype=float,
        )

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        ax1.imshow(img, interpolation="nearest", aspect="equal")
        ax1.set_title(title or f"{level.generator_name}  seed={level.seed}")
        ax1.axis("off")

        if show_path:
            path = level.shortest_path()
            if path:
                py = [p[0] for p in path]
                px = [p[1] for p in path]
                ax1.plot(px, py, color="cyan", linewidth=1.8, alpha=0.75,
                         label="Shortest path")

        patches = [mpatches.Patch(color=rgb[t], label=t.name) for t in TileType]
        ax1.legend(handles=patches, loc="lower left", fontsize=6,
                   ncol=2, framealpha=0.85)

        ax2.set_title(f"BFS Distance from START  seed={level.seed}")
        if level.start:
            dist_map = level.bfs_distances(level.start)
            heat = np.full((level.height, level.width), np.nan)
            for (r, c), d in dist_map.items():
                heat[r][c] = d
            im = ax2.imshow(heat, cmap="RdYlGn_r", interpolation="nearest",
                            aspect="equal")
            plt.colorbar(im, ax=ax2, shrink=0.85, label="steps")
        else:
            ax2.text(0.5, 0.5, "No START tile", ha="center", va="center",
                     transform=ax2.transAxes)
        ax2.axis("off")

        plt.tight_layout()

        if save:
            fname = f"level_{level.generator_name}_{level.seed}.png"
            plt.savefig(fname, dpi=110, bbox_inches="tight")
            print(f"[plot saved -> {fname}]")

        plt.show()

    def compare_plot(self, levels: List[Level], title: str = "") -> None:
        try:
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError:
            print("[visualizer] matplotlib not available")
            return

        rgb: dict = {
            TileType.VOID:  [0.08, 0.08, 0.08],
            TileType.WALL:  [0.42, 0.42, 0.42],
            TileType.FLOOR: [0.92, 0.88, 0.76],
            TileType.START: [0.10, 0.85, 0.10],
            TileType.END:   [0.90, 0.10, 0.10],
            TileType.ENEMY: [0.85, 0.20, 0.20],
            TileType.ITEM:  [0.95, 0.85, 0.05],
            TileType.TRAP:  [0.70, 0.10, 0.70],
        }

        n = len(levels)
        cols = min(3, n)
        rows = (n + cols - 1) // cols
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 6, rows * 4))
        if n == 1:
            axes = [[axes]]
        elif rows == 1:
            axes = [axes]

        for idx, level in enumerate(levels):
            ax = axes[idx // cols][idx % cols]
            img = np.array(
                [[rgb[level.at(r,c)] for c in range(level.width)]
                 for r in range(level.height)],
                dtype=float,
            )
            ax.imshow(img, interpolation="nearest", aspect="equal")
            path = level.shortest_path()
            if path:
                ax.plot([p[1] for p in path], [p[0] for p in path],
                        color="cyan", linewidth=1.2, alpha=0.7)
            ax.set_title(f"{level.generator_name} | seed {level.seed}", fontsize=9)
            ax.axis("off")

        for idx in range(n, rows * cols):
            axes[idx // cols][idx % cols].axis("off")

        if title:
            fig.suptitle(title, fontsize=12)
        plt.tight_layout()
        fname = "levels_comparison.png"
        plt.savefig(fname, dpi=100, bbox_inches="tight")
        print(f"[comparison saved -> {fname}]")
        plt.show()
