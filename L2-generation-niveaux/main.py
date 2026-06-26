import argparse
import sys
import os

if sys.platform == "win32":
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                      errors="replace", line_buffering=True)
    except AttributeError:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.evaluator import LevelEvaluator
from src.visualizer import LevelVisualizer
from src.wfc import WFCGenerator

try:
    from src.cpsat_gen import CPSATGenerator, HAS_ORTOOLS
except ImportError:
    HAS_ORTOOLS = False


evaluator  = LevelEvaluator()
visualizer = LevelVisualizer(use_color=True)


def _table_row(seed, m) -> str:
    pl = str(m["path_length"]) if m["path_exists"] else "N/A"
    return (
        f"{seed:>8} | {pl:>6} | {m['connectivity_ratio']:>6.1%} | "
        f"{m['floor_density']:>7.1%} | {m['enemy_count']:>6} | "
        f"{m['quality_score']:>7.3f}"
    )


def _table_header() -> str:
    return (
        f"{'Graine':>8} | {'Chemin':>6} | {'Conn.':>6} | "
        f"{'Densite':>7} | {'Ennem.':>6} | {'Qualite':>7}\n"
        + "-" * 8 + "-+-" + "-" * 6 + "-+-" + "-" * 6 + "-+-"
        + "-" * 7 + "-+-" + "-" * 6 + "-+-" + "-" * 7
    )


def demo_wfc(seeds, width, height, show_plot):
    print("\n" + "=" * 60)
    print("  WAVE FUNCTION COLLAPSE - Generation Multi-Graines")
    print("=" * 60)

    levels = []
    for seed in seeds:
        gen = WFCGenerator(
            width=width, height=height, seed=seed,
            floor_density_target=0.38,
            enemy_density=0.05,
            item_density=0.03,
            trap_density=0.015,
            symmetry=(seed % 3 == 0),
        )
        level = gen.generate()
        levels.append(level)
        sym_tag = "  [symetrique]" if gen.symmetry else ""
        visualizer.print_level(level,
                                f"WFC  seed={seed}{sym_tag}",
                                show_path=True)
        print()
        print(evaluator.report(level))

    print("\n" + "=" * 60)
    print("  TABLEAU RECAPITULATIF - WFC")
    print("=" * 60)
    print(_table_header())
    for level, seed in zip(levels, seeds):
        print(_table_row(seed, evaluator.evaluate(level)))

    if show_plot and levels:
        visualizer.compare_plot(levels, title="WFC - Niveaux Generes")
    return levels


def demo_cpsat(seeds, width, height, show_plot):
    if not HAS_ORTOOLS:
        print("\n[CP-SAT] OR-Tools non installe -> pip install ortools")
        return []

    print("\n" + "=" * 60)
    print("  CP-SAT (OR-Tools) - Generation Contrainte")
    print("=" * 60)

    levels = []
    for seed in seeds:
        print(f"\n  -> Resolution CP-SAT  seed={seed} ...", end="", flush=True)
        gen = CPSATGenerator(
            width=min(width, 22), height=min(height, 15),
            seed=seed,
            min_floor_ratio=0.18,
            max_floor_ratio=0.48,
            enemy_density=0.05,
            item_density=0.03,
            trap_density=0.015,
            symmetry=(seed % 2 == 0),
            timeout_seconds=25.0,
        )
        level = gen.generate()
        levels.append(level)
        print(f"  [{level.generator_name}]")
        visualizer.print_level(level, f"CP-SAT  seed={seed}", show_path=True)
        print()
        print(evaluator.report(level))

    print("\n" + "=" * 60)
    print("  TABLEAU RECAPITULATIF - CP-SAT")
    print("=" * 60)
    print(_table_header())
    for level, seed in zip(levels, seeds):
        print(_table_row(seed, evaluator.evaluate(level)))

    if show_plot and levels:
        visualizer.compare_plot(levels, title="CP-SAT - Niveaux Generes")
    return levels


def demo_parameter_sweep(width, height):
    print("\n" + "=" * 60)
    print("  VARIATION DE PARAMETRES  (graine fixe = 42)")
    print("=" * 60)

    configs = [
        dict(name="Vide-Ouvert",
             floor_density_target=0.55, enemy_density=0.02,
             item_density=0.01, trap_density=0.005, symmetry=False),
        dict(name="Dense-Serre",
             floor_density_target=0.22, enemy_density=0.04,
             item_density=0.02, trap_density=0.01, symmetry=False),
        dict(name="Combat",
             floor_density_target=0.40, enemy_density=0.10,
             item_density=0.01, trap_density=0.05, symmetry=False),
        dict(name="Tresor",
             floor_density_target=0.40, enemy_density=0.02,
             item_density=0.10, trap_density=0.02, symmetry=False),
        dict(name="Symetrique",
             floor_density_target=0.38, enemy_density=0.05,
             item_density=0.03, trap_density=0.015, symmetry=True),
    ]

    levels = []
    print(_table_header().replace("Graine", "Config.  ").replace(">8", ">12"))
    for cfg in configs:
        name = cfg.pop("name")
        gen = WFCGenerator(width=width, height=height, seed=42, **cfg)
        level = gen.generate()
        levels.append((name, level))
        m = evaluator.evaluate(level)
        pl = str(m["path_length"]) if m["path_exists"] else "N/A"
        print(
            f"{name:>12} | {pl:>6} | {m['connectivity_ratio']:>6.1%} | "
            f"{m['floor_density']:>7.1%} | {m['enemy_count']:>6} | "
            f"{m['quality_score']:>7.3f}"
        )

    for name, level in levels:
        if "Combat" in name:
            print()
            visualizer.print_level(level, f"Exemple : {name}", show_path=True)
            break

    return levels


def demo_compare_wfc_cpsat(width, height, show_plot):
    if not HAS_ORTOOLS:
        print("\n[Comparaison] OR-Tools non disponible.")
        return

    print("\n" + "=" * 60)
    print("  WFC  vs  CP-SAT - Comparaison Directe (seed=42)")
    print("=" * 60)

    seed = 42
    wfc_level = WFCGenerator(width=width, height=height, seed=seed).generate()
    cpsat_level = CPSATGenerator(width=min(width, 22), height=min(height, 15),
                                  seed=seed, timeout_seconds=20).generate()

    for label, level in [("WFC", wfc_level), ("CP-SAT", cpsat_level)]:
        visualizer.print_level(level, f"{label}  seed={seed}", show_path=True)
        print(evaluator.report(level))

    if show_plot:
        visualizer.compare_plot([wfc_level, cpsat_level],
                                 title="WFC vs CP-SAT - meme graine 42")


def main():
    parser = argparse.ArgumentParser(
        description="L2 - Generation Procedurale de Niveaux par Contraintes"
    )
    parser.add_argument(
        "--mode",
        choices=["wfc", "cpsat", "sweep", "compare", "all"],
        default="all",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 123, 7777])
    parser.add_argument("--width",   type=int, default=30)
    parser.add_argument("--height",  type=int, default=18)
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()
    show_plot = not args.no_plot

    print()
    print("=" * 56)
    print("  L2 - Generation Procedurale de Niveaux de Jeu")
    print("  WFC + CP-SAT + Evaluation Quantitative")
    print("=" * 56)
    print(f"  OR-Tools disponible : {'OUI' if HAS_ORTOOLS else 'NON (pip install ortools)'}")

    if args.mode in ("wfc", "all"):
        demo_wfc(args.seeds, args.width, args.height, show_plot)

    if args.mode in ("cpsat", "all"):
        demo_cpsat(args.seeds[:2], args.width, args.height, show_plot)

    if args.mode in ("sweep", "all"):
        demo_parameter_sweep(args.width, args.height)

    if args.mode in ("compare", "all"):
        demo_compare_wfc_cpsat(args.width, args.height, show_plot)

    print("\nDemonstration terminee.\n")


if __name__ == "__main__":
    main()
