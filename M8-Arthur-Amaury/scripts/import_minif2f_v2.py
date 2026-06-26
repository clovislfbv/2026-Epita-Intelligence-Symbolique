from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from m8_proof_agent.minif2f_v2 import write_benchmark_json  # noqa: E402


DATASETS = {
    "minif2f_v2s": "https://huggingface.co/datasets/roozbeh-yz/miniF2F_v2/resolve/main/miniF2F_v2s.jsonl",
    "minif2f_v2c": "https://huggingface.co/datasets/roozbeh-yz/miniF2F_v2/resolve/main/miniF2F_v2c.jsonl",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import miniF2F-v2 JSONL into local benchmark JSON.")
    parser.add_argument("--suite", choices=sorted(DATASETS), default="minif2f_v2s")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    output = args.output or ROOT / "benchmarks" / f"{args.suite}.json"
    with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
        temp_path = Path(handle.name)
        with urllib.request.urlopen(DATASETS[args.suite], timeout=60) as response:
            handle.write(response.read())

    try:
        written = write_benchmark_json(temp_path, output, suite=args.suite)
    finally:
        temp_path.unlink(missing_ok=True)
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
