from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BenchmarkTests(unittest.TestCase):
    def test_runtime_benchmark_suites_load(self) -> None:
        from m8_proof_agent.benchmarks import find_benchmark, load_benchmarks

        smoke = load_benchmarks(suite="smoke")
        subset = load_benchmarks(suite="minif2f_subset")
        full = load_benchmarks(suite="minif2f_v2s")

        self.assertEqual(find_benchmark("smoke_true", smoke).expected_tactics, ["trivial"])
        self.assertGreaterEqual(len(subset), 2)
        self.assertEqual(len(full), 488)


if __name__ == "__main__":
    unittest.main()
