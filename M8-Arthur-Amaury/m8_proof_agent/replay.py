from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .models import ProofTrace, model_to_json


ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = ROOT / "traces"


def load_trace(path: Path | str) -> ProofTrace:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    return ProofTrace(**data)


def save_trace(trace: ProofTrace, directory: Path | str = TRACE_DIR) -> Path:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    safe_run_id = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in trace.run_id).strip("._")
    filename = f"{safe_run_id or 'trace'}.json"
    path = root / filename
    path.write_text(model_to_json(trace), encoding="utf-8")
    return path


def latest_trace_path(directory: Path | str = TRACE_DIR) -> Path:
    root = Path(directory)
    paths = list(root.glob("*.json")) if root.exists() else []
    if not paths:
        raise FileNotFoundError("No trace is available for replay")
    return max(paths, key=lambda path: (path.stat().st_mtime_ns, path.name))


def latest_trace_path_for_theorem(theorem_id: str, directory: Path | str = TRACE_DIR) -> Path:
    root = Path(directory)
    paths = list(root.glob("*.json")) if root.exists() else []
    matching = []
    for path in paths:
        try:
            trace = load_trace(path)
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if trace.theorem.id == theorem_id:
            matching.append(path)
    if not matching:
        raise FileNotFoundError(f"No trace is available for theorem {theorem_id!r}")
    return max(matching, key=lambda path: (path.stat().st_mtime_ns, path.name))


def list_traces(directory: Path | str = TRACE_DIR) -> List[Dict[str, str]]:
    root = Path(directory)
    if not root.exists():
        return []
    traces: List[Dict[str, str]] = []
    paths = sorted(root.glob("*.json"), key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True)
    for path in paths:
        trace = load_trace(path)
        traces.append(
            {
                "file": path.name,
                "run_id": trace.run_id,
                "theorem_id": trace.theorem.id,
                "status": trace.status,
            }
        )
    return traces


def resolve_trace(filename: str) -> Path:
    path = (TRACE_DIR / filename).resolve()
    if not str(path).startswith(str(TRACE_DIR.resolve())):
        raise ValueError("Trace path escapes trace directory")
    return path
