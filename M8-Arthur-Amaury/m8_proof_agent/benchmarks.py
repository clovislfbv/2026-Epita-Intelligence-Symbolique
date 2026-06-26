from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .models import Benchmark


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "benchmarks"
KNOWN_SUITES = {"smoke", "minif2f_subset", "minif2f_v2s"}


def suite_path(suite: str) -> Path:
    safe_suite = suite if suite in KNOWN_SUITES else "smoke"
    return BENCHMARK_DIR / f"{safe_suite}.json"


def load_benchmarks(path: Path | str | None = None, suite: str = "smoke") -> List[Benchmark]:
    source = Path(path) if path is not None else suite_path(suite)
    raw = json.loads(source.read_text(encoding="utf-8"))
    return [Benchmark(**item) for item in raw]


def find_benchmark(theorem_id: str, benchmarks: Iterable[Benchmark]) -> Benchmark:
    for benchmark in benchmarks:
        if benchmark.id == theorem_id:
            return benchmark
    raise KeyError(f"No benchmark found for theorem id {theorem_id!r}")


def load_all_benchmarks() -> List[Benchmark]:
    all_items: List[Benchmark] = []
    for suite in ("smoke", "minif2f_subset", "minif2f_v2s"):
        path = suite_path(suite)
        if not path.exists():
            continue
        all_items.extend(load_benchmarks(suite=suite))
    return all_items
