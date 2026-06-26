"""Benchmark harness: run solvers over instances with a per-run timeout.

Each (solver, instance) pair runs in a worker process so a pathological case
(e.g. backtracking on a hard grid, or a non-converging GA) can be bounded by a
hard timeout without stalling the whole suite. Results are collected as plain
dict rows suitable for a pandas DataFrame / CSV.
"""

from __future__ import annotations

import csv
import multiprocessing as mp
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .board import Grid
from .generator import Instance
from .solvers import SOLVERS


@dataclass
class BenchRow:
    instance_id: str
    bucket: str
    solver: str
    seed: Optional[int]
    solved: bool
    timed_out: bool
    elapsed_s: Optional[float]
    nodes: Optional[int]
    peak_mem_bytes: Optional[int]
    #: Number of solutions enumerated on multi-solution grids. ``None`` for the
    #: single-solution runs, which never enumerate.
    solutions_found: Optional[int] = None


def _worker(solver_name: str, puzzle: str, seed: Optional[int], q: mp.Queue) -> None:
    try:
        cls = SOLVERS[solver_name]
        solver = cls(seed=seed) if solver_name == "genetic" else cls()
        result = solver.solve(Grid.parse(puzzle))
        q.put(
            {
                "solved": result.solved,
                "elapsed_s": result.elapsed_s,
                "nodes": result.nodes,
                "peak_mem_bytes": result.peak_mem_bytes,
            }
        )
    except Exception as exc:  # pragma: no cover - surfaced as a failed run
        q.put({"error": repr(exc)})


def _multi_worker(
    solver_name: str, puzzle: str, limit: int, q: mp.Queue
) -> None:
    """Enumerate up to ``limit`` solutions, measuring time and peak memory."""
    from .instrument import measure

    try:
        solver = SOLVERS[solver_name]()
        with measure() as m:
            solutions = solver.solve_all(Grid.parse(puzzle), limit=limit)
        q.put(
            {
                "solved": len(solutions) > 0,
                "elapsed_s": m.elapsed_s,
                "peak_mem_bytes": m.peak_mem_bytes,
                "solutions_found": len(solutions),
            }
        )
    except Exception as exc:  # pragma: no cover - surfaced as a failed run
        q.put({"error": repr(exc)})


def _run_proc(target, args, timeout: float):
    """Run ``target`` in a spawned process bounded by ``timeout``.

    Returns ``(payload, timed_out)`` where ``payload`` is the dict the worker
    pushed onto the queue (empty on timeout / no result).
    """
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    proc = ctx.Process(target=target, args=(*args, q))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return {}, True
    try:
        return q.get_nowait(), False
    except Exception:
        return {"error": "no result returned"}, False


def run_one(
    solver_name: str,
    instance: Instance,
    timeout: float,
    seed: Optional[int] = None,
) -> BenchRow:
    """Run a single solver on a single instance under a hard timeout."""
    payload, timed_out = _run_proc(
        _worker, (solver_name, instance.grid.to_line(), seed), timeout
    )
    solved = bool(payload.get("solved", False)) and not timed_out
    return BenchRow(
        instance_id=instance.id,
        bucket=instance.bucket,
        solver=solver_name,
        seed=seed,
        solved=solved,
        timed_out=timed_out,
        elapsed_s=None if timed_out else payload.get("elapsed_s"),
        nodes=None if timed_out else payload.get("nodes"),
        peak_mem_bytes=None if timed_out else payload.get("peak_mem_bytes"),
    )


def run_multi(
    solver_name: str,
    instance: Instance,
    timeout: float,
    limit: int,
) -> BenchRow:
    """Enumerate solutions of a multi-solution instance under a hard timeout.

    ``limit`` caps how many solutions to enumerate (one more than the expected
    count is enough to confirm non-uniqueness without an unbounded search).
    """
    payload, timed_out = _run_proc(
        _multi_worker, (solver_name, instance.grid.to_line(), limit), timeout
    )
    solved = bool(payload.get("solved", False)) and not timed_out
    return BenchRow(
        instance_id=instance.id,
        bucket=instance.bucket,
        solver=solver_name,
        seed=None,
        solved=solved,
        timed_out=timed_out,
        elapsed_s=None if timed_out else payload.get("elapsed_s"),
        nodes=None,
        peak_mem_bytes=None if timed_out else payload.get("peak_mem_bytes"),
        solutions_found=None if timed_out else payload.get("solutions_found"),
    )


def run_benchmark(
    instances: List[Instance],
    solver_names: List[str],
    timeout: float = 30.0,
    ga_seeds: Optional[List[int]] = None,
) -> List[BenchRow]:
    """Run every solver on every instance. The genetic solver runs once per seed."""
    ga_seeds = ga_seeds or [1, 2, 3]
    rows: List[BenchRow] = []
    for inst in instances:
        if inst.bucket == "multi":
            # Multi-solution grids are evaluated by *enumeration* rather than
            # by single solve: only solvers that can list solutions apply, and
            # we record how many were found (capped just above the expected
            # count to confirm non-uniqueness cheaply).
            limit = inst.expected_solutions + 1
            for name in solver_names:
                if SOLVERS[name].supports_multi:
                    rows.append(run_multi(name, inst, timeout, limit))
            continue
        for name in solver_names:
            if name == "genetic":
                for seed in ga_seeds:
                    rows.append(run_one(name, inst, timeout, seed=seed))
            else:
                rows.append(run_one(name, inst, timeout))
    return rows


def write_csv(rows: List[BenchRow], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
