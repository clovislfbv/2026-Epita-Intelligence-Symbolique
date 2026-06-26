from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class AppApiTests(unittest.TestCase):
    def test_health_and_benchmarks_routes_support_the_ui(self) -> None:
        import app

        health_status, health_payload = app.api_response("GET", "/api/health", b"")
        benchmarks_status, benchmarks_payload = app.api_response("GET", "/api/benchmarks", b"")

        self.assertEqual(health_status, 200)
        self.assertIn("providers", health_payload)
        self.assertEqual(benchmarks_status, 200)
        suites = {item["suite"] for item in benchmarks_payload["benchmarks"]}
        self.assertIn("smoke", suites)
        self.assertIn("minif2f_subset", suites)

    def test_run_saves_trace_that_replay_can_open(self) -> None:
        import app
        from m8_proof_agent.models import LeanResult

        original_verify = app.VERIFY_FN
        original_probe = app.GOAL_PROBE_FN
        original_get_provider = app.get_provider
        original_trace_dir = app.TRACE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            app.TRACE_DIR = Path(tmp)
            app.VERIFY_FN = lambda imports, statement, proof, **kwargs: LeanResult(success=True, status="success", output="ok")
            app.GOAL_PROBE_FN = lambda imports, statement, **kwargs: LeanResult(success=False, status="failed", errors="⊢ True")
            app.get_provider = lambda name, model="": FakeProvider()
            try:
                status, payload = app.api_response(
                    "POST",
                    "/api/run",
                    json.dumps({"theorem_id": "smoke_true", "suite": "smoke", "provider": "openai"}).encode("utf-8"),
                )
                replay_status, replay_payload = app.api_response("POST", "/api/replay", b"{}")
            finally:
                app.VERIFY_FN = original_verify
                app.GOAL_PROBE_FN = original_probe
                app.get_provider = original_get_provider
                app.TRACE_DIR = original_trace_dir

        self.assertEqual(status, 200)
        self.assertEqual(payload["trace"]["status"], "success")
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay_payload["trace"]["run_id"], payload["trace"]["run_id"])

    def test_run_passes_mcts_strategy_to_graph(self) -> None:
        import app
        from m8_proof_agent.models import ProofTrace

        original_get_provider = app.get_provider
        original_trace_dir = app.TRACE_DIR
        original_run_proof_graph = app.run_proof_graph
        seen = {}
        with tempfile.TemporaryDirectory() as tmp:
            app.TRACE_DIR = Path(tmp)
            app.get_provider = lambda name, model="": FakeProvider()

            def fake_run_proof_graph(theorem, provider, **kwargs):
                seen.update(kwargs)
                return ProofTrace(
                    run_id="run-search-strategy",
                    theorem=theorem,
                    mode="real",
                    provider=provider.name,
                    model=provider.model,
                    status="success",
                    final_proof="trivial",
                )

            app.run_proof_graph = fake_run_proof_graph
            try:
                status, _payload = app.api_response(
                    "POST",
                    "/api/run",
                    json.dumps(
                        {
                            "theorem_id": "smoke_true",
                            "suite": "smoke",
                            "provider": "openai",
                            "search_strategy": "mcts",
                            "mcts_iterations": 7,
                        }
                    ).encode("utf-8"),
                )
            finally:
                app.get_provider = original_get_provider
                app.run_proof_graph = original_run_proof_graph
                app.TRACE_DIR = original_trace_dir

        self.assertEqual(status, 200)
        self.assertEqual(seen["search_strategy"], "mcts")
        self.assertEqual(seen["mcts_iterations"], 7)

    def test_stream_run_returns_events_and_final_trace(self) -> None:
        import app
        from m8_proof_agent.models import LeanResult

        original_verify = app.VERIFY_FN
        original_probe = app.GOAL_PROBE_FN
        original_get_provider = app.get_provider
        original_trace_dir = app.TRACE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            app.TRACE_DIR = Path(tmp)
            app.VERIFY_FN = lambda imports, statement, proof, **kwargs: LeanResult(success=True, status="success", output="ok")
            app.GOAL_PROBE_FN = lambda imports, statement, **kwargs: LeanResult(success=False, status="failed", errors="⊢ True")
            app.get_provider = lambda name, model="": FakeProvider()
            try:
                lines = list(
                    app.stream_run_lines(
                        json.dumps({"theorem_id": "smoke_true", "suite": "smoke", "provider": "openai"}).encode("utf-8")
                    )
                )
            finally:
                app.VERIFY_FN = original_verify
                app.GOAL_PROBE_FN = original_probe
                app.get_provider = original_get_provider
                app.TRACE_DIR = original_trace_dir

        payloads = [json.loads(line.decode("utf-8")) for line in lines]
        self.assertTrue(any(item["type"] == "event" for item in payloads))
        self.assertEqual(payloads[-1]["type"], "trace")
        self.assertEqual(payloads[-1]["trace"]["status"], "success")

    def test_stream_suite_scores_results(self) -> None:
        import app
        from m8_proof_agent.models import Benchmark, LeanResult

        benchmarks = [
            Benchmark(id="suite_success", title="Suite success", suite="smoke", difficulty="easy", imports="", statement="theorem suite_success : True := by", source="unit-test"),
            Benchmark(id="suite_failed", title="Suite failed", suite="smoke", difficulty="easy", imports="", statement="theorem suite_failed : True := by", source="unit-test"),
        ]

        original_verify = app.VERIFY_FN
        original_probe = app.GOAL_PROBE_FN
        original_get_provider = app.get_provider
        original_trace_dir = app.TRACE_DIR
        original_load_benchmarks = app.load_benchmarks
        with tempfile.TemporaryDirectory() as tmp:
            app.TRACE_DIR = Path(tmp)
            app.get_provider = lambda name, model="": FakeProvider()
            app.load_benchmarks = lambda suite="smoke": benchmarks
            app.GOAL_PROBE_FN = lambda imports, statement, **kwargs: LeanResult(success=False, status="failed", errors="⊢ True")

            def verify(imports, statement, proof, **kwargs):
                success = "suite_success" in statement
                return LeanResult(success=success, status="success" if success else "failed", output="ok", errors="" if success else "bad proof")

            app.VERIFY_FN = verify
            try:
                with redirect_stdout(StringIO()):
                    lines = list(app.stream_suite_lines(json.dumps({"suite": "smoke", "provider": "openai"}).encode("utf-8")))
            finally:
                app.VERIFY_FN = original_verify
                app.GOAL_PROBE_FN = original_probe
                app.get_provider = original_get_provider
                app.TRACE_DIR = original_trace_dir
                app.load_benchmarks = original_load_benchmarks

        payloads = [json.loads(line.decode("utf-8")) for line in lines]
        self.assertEqual([item["type"] for item in payloads], ["result", "result", "score"])
        self.assertEqual(payloads[-1]["score"]["solved"], 1)
        self.assertEqual(payloads[-1]["score"]["attempted"], 2)


class FakeProvider:
    name = "openai"
    model = "gpt-test"

    def generate_candidates(self, context):
        from m8_proof_agent.models import ProofCandidate

        return [ProofCandidate(proof="trivial", rationale="unit test")]


if __name__ == "__main__":
    unittest.main()
