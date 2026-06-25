from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class GraphTests(unittest.TestCase):
    def _benchmark(self):
        from m8_proof_agent.models import Benchmark

        return Benchmark(
            id="smoke_true",
            title="True introduction",
            suite="smoke",
            difficulty="easy",
            imports="",
            statement="theorem smoke_true : True := by",
            source="unit-test",
            expected_tactics=["trivial"],
        )

    def test_beam_search_verifies_competing_candidates(self) -> None:
        from m8_proof_agent.graph import ProofCandidate, run_proof_graph
        from m8_proof_agent.models import LeanResult

        class Provider:
            name = "fake"
            model = "unit"

            def generate_candidates(self, context):
                return [
                    ProofCandidate(proof="exact bad", rationale="bad branch"),
                    ProofCandidate(proof="trivial", rationale="good branch"),
                ]

        def verify(imports: str, statement: str, proof: str) -> LeanResult:
            return LeanResult(success=proof == "trivial", status="success" if proof == "trivial" else "failed", errors="bad")

        trace = run_proof_graph(self._benchmark(), Provider(), verify_fn=verify, beam_width=2)

        self.assertEqual(trace.status, "success")
        self.assertEqual(trace.final_proof, "trivial")
        self.assertTrue(any(event.kind == "beam_started" for event in trace.events))

    def test_mcts_keeps_valid_prefix_and_finds_final_proof(self) -> None:
        from m8_proof_agent.graph import ProofCandidate, run_proof_graph
        from m8_proof_agent.models import LeanResult

        class Provider:
            name = "fake"
            model = "unit"

            def generate_candidates(self, context):
                if context["proof_prefix"] == "":
                    return [ProofCandidate(proof="intro hp", rationale="open premise")]
                return [ProofCandidate(proof="exact hp", rationale="close goal")]

        def verify(imports: str, statement: str, proof: str) -> LeanResult:
            if proof == "intro hp\nexact hp":
                return LeanResult(success=True, status="success", output="ok")
            if proof == "intro hp\nskip":
                return LeanResult(success=False, status="failed", errors="unsolved goals\nhp : True\n⊢ True")
            return LeanResult(success=False, status="failed", errors="bad")

        trace = run_proof_graph(
            self._benchmark(),
            Provider(),
            verify_fn=verify,
            search_strategy="mcts",
            beam_width=1,
            mcts_iterations=3,
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(trace.final_proof, "intro hp\nexact hp")
        self.assertTrue(any(event.kind == "mcts_node_kept" for event in trace.events))

    def test_setup_needed_stops_search(self) -> None:
        from m8_proof_agent.graph import ProofCandidate, run_proof_graph
        from m8_proof_agent.models import LeanResult

        class Provider:
            name = "fake"
            model = "unit"

            def generate_candidates(self, context):
                return [ProofCandidate(proof="trivial", rationale="try")]

        def verify(imports: str, statement: str, proof: str) -> LeanResult:
            return LeanResult(success=False, status="setup_needed", errors="lean not found")

        trace = run_proof_graph(self._benchmark(), Provider(), verify_fn=verify)

        self.assertEqual(trace.status, "setup_needed")
        self.assertEqual(trace.error, "lean not found")


if __name__ == "__main__":
    unittest.main()
