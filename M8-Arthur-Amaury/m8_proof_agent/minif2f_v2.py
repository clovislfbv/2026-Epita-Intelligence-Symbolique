from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .models import Benchmark, model_to_dict


def parse_jsonl_rows(rows: Iterable[str], suite: str) -> List[Benchmark]:
    benchmarks: List[Benchmark] = []
    for raw in rows:
        line = raw.strip()
        if not line:
            continue
        item = json.loads(line)
        name = str(item["name"])
        split = str(item.get("split") or "unknown")
        informal = str(item.get("informal_statement") or item.get("informal statement") or "")
        proof = str(item.get("formal_proof") or "").strip()
        expected_tactics = [proof] if proof and proof != "sorry" else []
        benchmarks.append(
            Benchmark(
                id=name,
                title=name.replace("_", " "),
                suite=suite,
                difficulty=split,
                imports=str(item.get("header") or "").strip(),
                statement=str(item["formal_statement"]).strip(),
                source=f"miniF2F-v2 {split}",
                expected_tactics=expected_tactics,
                description=informal,
            )
        )
    return benchmarks


def write_benchmark_json(jsonl_path: Path | str, output_path: Path | str, suite: str) -> Path:
    source = Path(jsonl_path)
    target = Path(output_path)
    benchmarks = parse_jsonl_rows(source.read_text(encoding="utf-8").splitlines(), suite=suite)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [model_to_dict(item) for item in benchmarks]
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
