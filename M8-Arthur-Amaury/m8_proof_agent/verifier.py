from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Callable, List, Optional

from .models import LeanResult


CommandRunner = Callable[..., subprocess.CompletedProcess]


def find_lean() -> Optional[str]:
    return shutil.which("lean")


def build_lean_file(imports: str, statement: str, proof: str) -> str:
    parts = []
    if imports.strip():
        parts.append(imports.strip())
    statement_text = statement.rstrip()
    proof_text = normalize_proof_body(proof)
    if statement_text.endswith("by"):
        parts.append(f"{statement_text}\n  {proof_text.replace(chr(10), chr(10) + '  ')}")
    else:
        parts.append(f"{statement_text}\n{proof_text}")
    return "\n\n".join(parts) + "\n"


def normalize_proof_body(proof: str) -> str:
    proof_text = proof.strip()
    if proof_text == "by":
        return ""
    if proof_text.startswith("by\n"):
        return proof_text.split("\n", 1)[1].strip()
    return proof_text


def verify_lean(
    imports: str,
    statement: str,
    proof: str,
    lean_project_dir: str | None = None,
    runner: CommandRunner = subprocess.run,
    timeout: int = 20,
) -> LeanResult:
    lean = find_lean()
    if not lean:
        return LeanResult(success=False, status="setup_needed", errors="lean binary not found")
    if requires_lake_project(imports) and not lean_project_dir:
        return LeanResult(
            success=False,
            status="setup_needed",
            errors="Mathlib imports require a configured Lake project. Set M8_LEAN_PROJECT_DIR to a Lean project with Mathlib.",
        )

    source = build_lean_file(imports, statement, proof)
    with tempfile.TemporaryDirectory(prefix="m8-lean-") as tmp:
        path = Path(tmp) / "Candidate.lean"
        path.write_text(source, encoding="utf-8")
        command: List[str]
        cwd = None
        if lean_project_dir:
            command = ["lake", "env", "lean", str(path)]
            cwd = lean_project_dir
        else:
            command = [lean, str(path)]
        started = perf_counter()
        try:
            completed = runner(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            elapsed = int((perf_counter() - started) * 1000)
            return LeanResult(success=False, status="timeout", errors="Lean verification timed out", command=command, elapsed_ms=elapsed)
        elapsed = int((perf_counter() - started) * 1000)

    output = (completed.stdout or "").strip()
    errors = (completed.stderr or "").strip()
    success = completed.returncode == 0
    if not success and not errors:
        errors = output
    if not success and is_mathlib_cache_missing(errors or output):
        return LeanResult(
            success=False,
            status="setup_needed",
            output=output,
            errors=(
                "Mathlib is configured but compiled artifacts are missing. "
                f"Run `cd {lean_project_dir}` then `lake exe cache get` "
                "or `lake build Mathlib`."
            ),
            command=command,
            elapsed_ms=elapsed,
        )
    return LeanResult(
        success=success,
        status="success" if success else "failed",
        output=output,
        errors=errors,
        command=command,
        elapsed_ms=elapsed,
    )


def probe_lean_goal(
    imports: str,
    statement: str,
    lean_project_dir: str | None = None,
    runner: CommandRunner = subprocess.run,
    timeout: int = 20,
) -> LeanResult:
    return verify_lean(
        imports,
        statement,
        "skip",
        lean_project_dir=lean_project_dir,
        runner=runner,
        timeout=timeout,
    )


def requires_lake_project(imports: str) -> bool:
    return any(line.strip().startswith("import Mathlib") for line in imports.splitlines())


def is_mathlib_cache_missing(message: str) -> bool:
    return "Mathlib.olean" in message and "does not exist" in message
