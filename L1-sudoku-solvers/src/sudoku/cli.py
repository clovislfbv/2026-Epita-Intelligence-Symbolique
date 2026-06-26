"""Command-line interface: ``sudoku-bench solve | benchmark | report``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .board import Grid
from .generator import BUCKET_ORDER, filter_buckets, load_instances
from .solvers import SOLVERS


def _resolve_solvers(names: List[str]) -> List[str]:
    if not names or "all" in names:
        return list(SOLVERS.keys())
    unknown = [n for n in names if n not in SOLVERS]
    if unknown:
        raise SystemExit(f"unknown solver(s): {', '.join(unknown)}")
    return names


def cmd_solve(args) -> int:
    text = args.grid
    # Treat the argument as a file only if it is short enough to be a path
    # (an 81-char grid string is not), guarding against odd filesystem calls.
    if len(text) < 4096 and Path(text).exists():
        text = Path(text).read_text()
    grid = Grid.parse(text)
    name = args.solver
    if name not in SOLVERS:
        raise SystemExit(f"unknown solver: {name}")
    solver = SOLVERS[name]()
    result = solver.solve(grid)
    print(f"solver={result.solver} solved={result.solved} "
          f"time={result.elapsed_s:.4f}s nodes={result.nodes} "
          f"peak_mem={result.peak_mem_bytes}")
    if result.solution:
        print(result.solution.to_pretty())
    return 0 if result.solved else 1


def cmd_benchmark(args) -> int:
    from .benchmark import run_benchmark, write_csv

    instances = filter_buckets(load_instances(), args.buckets)
    solver_names = _resolve_solvers(args.solvers)
    rows = run_benchmark(instances, solver_names, timeout=args.timeout)
    out = Path(args.out)
    write_csv(rows, out)
    solved = sum(1 for r in rows if r.solved)
    print(f"ran {len(rows)} solves ({solved} solved) -> {out}")
    return 0


def cmd_report(args) -> int:
    from .report import generate_report

    out = generate_report(Path(args.inp), Path(args.out))
    print(f"report written -> {out}")
    return 0


def cmd_generate(args) -> int:
    import json

    from .generator import count_solutions, generate_puzzle

    records = []
    for i in range(args.count):
        seed = None if args.seed is None else args.seed + i
        grid = generate_puzzle(args.bucket, seed=seed, holes=args.holes)
        line = grid.to_line()
        expected = count_solutions(grid, limit=50) if args.bucket == "multi" else 1
        suffix = "manual" if seed is None else str(seed)
        records.append(
            {
                "id": f"{args.bucket}-gen-{suffix}-{i}" if seed is None else f"{args.bucket}-gen-{seed}",
                "bucket": args.bucket,
                "puzzle": line,
                "note": "généré",
                "expected_solutions": expected,
            }
        )
        print(f"# {args.bucket} clues={grid.num_clues} solutions={expected}")
        print(line)

    if args.append:
        path = Path(args.append)
        data = json.loads(path.read_text()) if path.exists() else {"instances": []}
        existing = {r["id"] for r in data["instances"]}
        added = 0
        for rec in records:
            if rec["id"] in existing:
                continue
            # expected_solutions defaults to 1 in the loader; omit it when 1.
            if rec["expected_solutions"] == 1:
                rec = {k: v for k, v in rec.items() if k != "expected_solutions"}
            data["instances"].append(rec)
            added += 1
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"appended {added} instance(s) -> {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sudoku-bench", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("solve", help="solve a single grid")
    s.add_argument("grid", help="81-char grid string or path to a grid file")
    s.add_argument("--solver", default="cp_sat", choices=list(SOLVERS), help="solver to use")
    s.set_defaults(func=cmd_solve)

    b = sub.add_parser("benchmark", help="run solvers over the instance battery")
    b.add_argument("--solvers", nargs="+", default=["all"], help="solver names or 'all'")
    b.add_argument("--buckets", nargs="+", default=["all"], help="difficulty buckets or 'all'")
    b.add_argument("--timeout", type=float, default=30.0, help="per-run timeout (s)")
    b.add_argument("--out", default="benchmarks/results/results.csv", help="output CSV path")
    b.set_defaults(func=cmd_benchmark)

    r = sub.add_parser("report", help="render a markdown report from a results CSV")
    r.add_argument("--in", dest="inp", default="benchmarks/results/results.csv")
    r.add_argument("--out", default="reports/report.md")
    r.set_defaults(func=cmd_report)

    g = sub.add_parser("generate", help="generate puzzle(s) of a given difficulty")
    g.add_argument(
        "--bucket",
        default="medium",
        choices=BUCKET_ORDER,
        help="difficulty bucket (uniqueness certified by DLX; 'multi' is non-unique)",
    )
    g.add_argument("--count", type=int, default=1, help="how many puzzles to generate")
    g.add_argument("--seed", type=int, default=None, help="base RNG seed (incremented per puzzle)")
    g.add_argument("--holes", type=int, default=None, help="override the number of holes to dig")
    g.add_argument(
        "--append",
        metavar="JSON",
        help="append generated puzzles to this instances JSON file",
    )
    g.set_defaults(func=cmd_generate)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
