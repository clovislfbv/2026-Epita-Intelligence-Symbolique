from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class VerifierTests(unittest.TestCase):
    def test_build_lean_file_strips_extra_by_from_provider_body(self) -> None:
        from m8_proof_agent.verifier import build_lean_file

        source = build_lean_file("", "theorem t : True := by", "by\n  trivial")

        self.assertIn("theorem t : True := by\n  trivial", source)
        self.assertNotIn("by\n  by", source)

    def test_probe_lean_goal_uses_skip_to_capture_unsolved_goals(self) -> None:
        from m8_proof_agent import verifier

        original_find_lean = verifier.find_lean
        verifier.find_lean = lambda: "/usr/bin/lean"
        seen = {}

        def runner(*args, **kwargs):
            seen["source"] = Path(args[0][-1]).read_text(encoding="utf-8")
            return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="unsolved goals\n⊢ True")

        try:
            result = verifier.probe_lean_goal("", "theorem t : True := by", runner=runner)
        finally:
            verifier.find_lean = original_find_lean

        self.assertIn("skip", seen["source"])
        self.assertEqual(result.errors, "unsolved goals\n⊢ True")

    def test_mathlib_import_without_project_returns_setup_needed(self) -> None:
        from m8_proof_agent import verifier

        original_find_lean = verifier.find_lean
        verifier.find_lean = lambda: "/usr/bin/lean"
        try:
            result = verifier.verify_lean("import Mathlib", "theorem t : True := by", "trivial")
        finally:
            verifier.find_lean = original_find_lean

        self.assertEqual(result.status, "setup_needed")
        self.assertIn("Lake project", result.errors)


if __name__ == "__main__":
    unittest.main()
