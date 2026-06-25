from __future__ import annotations

import inspect
from time import perf_counter
from typing import Callable, List, Optional
from uuid import uuid4

from .models import AgentRole, Benchmark, LeanResult, ProofAttempt, ProofCandidate, ProofTrace, TraceEvent
from .providers import CandidateProvider, ProviderError
from .verifier import verify_lean


VerifyFn = Callable[..., LeanResult]
GoalProbeFn = Callable[..., LeanResult]
EventSink = Callable[[TraceEvent], None]


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
    except Exception:
        return False
    return True


class EventBuilder:
    def __init__(self, started_at: float, sink: Optional[EventSink] = None) -> None:
        self.events: List[TraceEvent] = []
        self.started_at = started_at
        self.sink = sink

    def add(self, kind: str, agent: AgentRole, message: str, **payload: object) -> None:
        event_payload = dict(payload)
        event_payload.setdefault("elapsed_ms", int((perf_counter() - self.started_at) * 1000))
        event = TraceEvent(
            index=len(self.events) + 1,
            kind=kind,
            agent=agent,
            message=message,
            payload=event_payload,
        )
        self.events.append(event)
        if self.sink:
            self.sink(event)


def _verify_candidate(verify_fn: VerifyFn, theorem: Benchmark, proof: str) -> LeanResult:
    signature = inspect.signature(verify_fn)
    supports_project_dir = "lean_project_dir" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )
    if supports_project_dir:
        return verify_fn(theorem.imports, theorem.statement, proof, lean_project_dir=theorem.lean_project_dir)
    return verify_fn(theorem.imports, theorem.statement, proof)


def _probe_goal(goal_probe_fn: GoalProbeFn, theorem: Benchmark) -> LeanResult:
    signature = inspect.signature(goal_probe_fn)
    supports_project_dir = "lean_project_dir" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )
    if supports_project_dir:
        return goal_probe_fn(theorem.imports, theorem.statement, lean_project_dir=theorem.lean_project_dir)
    return goal_probe_fn(theorem.imports, theorem.statement)


def _append_proof_step(prefix: str, step: str) -> str:
    clean_prefix = prefix.strip()
    clean_step = step.strip()
    if not clean_prefix:
        return clean_step
    if not clean_step:
        return clean_prefix
    return f"{clean_prefix}\n{clean_step}"


def _looks_like_open_goal(result: LeanResult) -> bool:
    message = f"{result.errors}\n{result.output}".lower()
    return "unsolved goals" in message or "⊢" in message


def run_proof_graph(
    theorem: Benchmark,
    provider: CandidateProvider,
    verify_fn: VerifyFn = verify_lean,
    max_attempts: int = 3,
    beam_width: int = 1,
    search_strategy: str = "beam",
    mcts_iterations: int = 12,
    goal_probe_fn: Optional[GoalProbeFn] = None,
    event_sink: Optional[EventSink] = None,
) -> ProofTrace:
    started = perf_counter()
    events = EventBuilder(started_at=started, sink=event_sink)
    attempts: List[ProofAttempt] = []
    errors: List[str] = []
    final_proof = None
    status = "failed"
    error = ""
    goal_state = ""
    effective_beam_width = max(1, min(beam_width, 5))
    effective_strategy = search_strategy if search_strategy in {"beam", "mcts"} else "beam"
    effective_mcts_iterations = max(1, min(mcts_iterations, 40))

    events.add("run_started", AgentRole.ORCHESTRATOR, f"Starting proof search for {theorem.id}")
    events.add("plan_created", AgentRole.DECOMPOSER, "Created tactic-oriented proof plan", expected_tactics=theorem.expected_tactics)
    if goal_probe_fn:
        events.add("goal_probe_started", AgentRole.VERIFIER, "Asking Lean for the initial proof goal")
        goal_probe = _probe_goal(goal_probe_fn, theorem)
        goal_state = goal_probe.errors or goal_probe.output
        events.add(
            "goal_probe_finished" if goal_state else "goal_probe_skipped",
            AgentRole.VERIFIER,
            "Lean returned an initial goal state" if goal_state else "Lean goal probe produced no goal text",
            status=goal_probe.status,
            goal_state=goal_state,
            command=goal_probe.command,
            probe_elapsed_ms=goal_probe.elapsed_ms,
        )

    if effective_strategy == "mcts":
        events.add(
            "mcts_started",
            AgentRole.ORCHESTRATOR,
            "Starting Monte Carlo tree search over proof prefixes",
            iterations=effective_mcts_iterations,
            beam_width=effective_beam_width,
        )
        frontier = [{"proof": "", "goal_state": goal_state, "depth": 0}]
        for iteration in range(1, effective_mcts_iterations + 1):
            if not frontier:
                error = "MCTS frontier exhausted"
                events.add("mcts_frontier_exhausted", AgentRole.ORCHESTRATOR, error, iteration=iteration)
                break
            node = frontier.pop(0)
            prefix = str(node["proof"])
            node_goal_state = str(node["goal_state"])
            events.add(
                "mcts_selected",
                AgentRole.TACTIC,
                "Selected proof-prefix node for expansion",
                iteration=iteration,
                proof_prefix=prefix,
                frontier_size=len(frontier),
                depth=node["depth"],
            )
            context = {
                "theorem_id": theorem.id,
                "imports": theorem.imports,
                "statement": theorem.statement,
                "expected_tactics": theorem.expected_tactics,
                "errors": errors[-3:],
                "goal_state": node_goal_state,
                "candidate_count": effective_beam_width,
                "beam_width": effective_beam_width,
                "search_strategy": "mcts",
                "proof_prefix": prefix,
                "iteration": iteration,
            }
            try:
                candidates = provider.generate_candidates(context)[:effective_beam_width]
            except ProviderError as exc:
                status = "provider_error"
                error = str(exc)
                events.add("provider_error", AgentRole.TACTIC, error)
                break
            if not candidates:
                errors.append("Provider returned no MCTS candidates")
                events.add("mcts_node_empty", AgentRole.TACTIC, errors[-1], iteration=iteration, proof_prefix=prefix)
                continue

            for branch_index, candidate in enumerate(candidates, start=1):
                proof = _append_proof_step(prefix, candidate.proof)
                events.add(
                    "mcts_expanded",
                    AgentRole.TACTIC,
                    candidate.rationale,
                    proof_prefix=prefix,
                    proof=proof,
                    branch_index=branch_index,
                    beam_width=effective_beam_width,
                    iteration=iteration,
                )
                verification = _verify_candidate(verify_fn, theorem, proof)
                attempts.append(
                    ProofAttempt(
                        iteration=iteration,
                        agent=AgentRole.TACTIC,
                        proof=proof,
                        rationale=candidate.rationale,
                        verification=verification,
                    )
                )
                events.add(
                    "verification_finished",
                    AgentRole.VERIFIER,
                    "Lean accepted the MCTS branch" if verification.success else "Lean rejected the MCTS branch as a complete proof",
                    status=verification.status,
                    errors=verification.errors,
                    output=verification.output,
                    command=verification.command,
                    branch_index=branch_index,
                    beam_width=effective_beam_width,
                    search_strategy="mcts",
                    verification_elapsed_ms=verification.elapsed_ms,
                )
                if verification.success:
                    final_proof = proof
                    status = "success"
                    events.add(
                        "final_verified",
                        AgentRole.ASSEMBLER,
                        "Final MCTS branch accepted by Lean",
                        proof=final_proof,
                        branch_index=branch_index,
                        beam_width=effective_beam_width,
                    )
                    break
                if verification.status == "setup_needed":
                    status = "setup_needed"
                    error = verification.errors or "Lean setup is missing"
                    events.add("setup_needed", AgentRole.VERIFIER, error)
                    break

                prefix_probe = _verify_candidate(verify_fn, theorem, _append_proof_step(proof, "skip"))
                probe_goal_state = prefix_probe.errors or prefix_probe.output
                events.add(
                    "mcts_prefix_probe_finished",
                    AgentRole.VERIFIER,
                    "Lean kept this prefix alive" if _looks_like_open_goal(prefix_probe) else "Lean pruned this prefix",
                    status=prefix_probe.status,
                    goal_state=probe_goal_state,
                    proof=proof,
                    branch_index=branch_index,
                    command=prefix_probe.command,
                    probe_elapsed_ms=prefix_probe.elapsed_ms,
                )
                if _looks_like_open_goal(prefix_probe):
                    frontier.append({"proof": proof, "goal_state": probe_goal_state, "depth": int(node["depth"]) + 1})
                    events.add(
                        "mcts_node_kept",
                        AgentRole.TACTIC,
                        "Queued valid proof prefix for later expansion",
                        proof=proof,
                        frontier_size=len(frontier),
                    )
                else:
                    errors.append(probe_goal_state or verification.errors or "Lean pruned MCTS branch")
                    events.add("mcts_node_pruned", AgentRole.TACTIC, errors[-1], proof=proof)
            if status in {"success", "setup_needed", "provider_error"}:
                break
        if status == "failed" and not error and errors:
            events.add("repair_requested", AgentRole.REPAIR, "MCTS ended with Lean feedback", errors=errors[-3:])
    else:
        for iteration in range(1, max(1, min(max_attempts, 8)) + 1):
            agent = AgentRole.TACTIC if iteration == 1 else AgentRole.REPAIR
            events.add("agent_started", agent, f"Generating candidate proof for iteration {iteration}")
            events.add(
                "beam_started",
                agent,
                f"Requesting up to {effective_beam_width} proof candidate branch(es)",
                iteration=iteration,
                beam_width=effective_beam_width,
            )
            context = {
                "theorem_id": theorem.id,
                "imports": theorem.imports,
                "statement": theorem.statement,
                "expected_tactics": theorem.expected_tactics,
                "errors": errors[-3:],
                "goal_state": goal_state,
                "candidate_count": effective_beam_width,
                "beam_width": effective_beam_width,
                "search_strategy": "beam",
                "proof_prefix": "",
                "iteration": iteration,
            }
            try:
                candidates = provider.generate_candidates(context)[:effective_beam_width]
            except ProviderError as exc:
                status = "provider_error"
                error = str(exc)
                events.add("provider_error", agent, error)
                break
            if not candidates:
                errors.append("Provider returned no proof candidates")
                events.add("beam_empty", agent, errors[-1], iteration=iteration, beam_width=effective_beam_width)
                continue

            for branch_index, candidate in enumerate(candidates, start=1):
                events.add(
                    "candidate_created",
                    agent,
                    candidate.rationale,
                    proof=candidate.proof,
                    branch_index=branch_index,
                    beam_width=effective_beam_width,
                )
                verification = _verify_candidate(verify_fn, theorem, candidate.proof)
                attempts.append(
                    ProofAttempt(
                        iteration=iteration,
                        agent=agent,
                        proof=candidate.proof,
                        rationale=candidate.rationale,
                        verification=verification,
                    )
                )
                events.add(
                    "verification_finished",
                    AgentRole.VERIFIER,
                    "Lean accepted the candidate" if verification.success else "Lean rejected the candidate",
                    status=verification.status,
                    errors=verification.errors,
                    output=verification.output,
                    command=verification.command,
                    branch_index=branch_index,
                    beam_width=effective_beam_width,
                    verification_elapsed_ms=verification.elapsed_ms,
                )
                if verification.success:
                    final_proof = candidate.proof
                    status = "success"
                    events.add(
                        "final_verified",
                        AgentRole.ASSEMBLER,
                        "Final proof accepted by Lean",
                        proof=final_proof,
                        branch_index=branch_index,
                        beam_width=effective_beam_width,
                    )
                    break
                if verification.status == "setup_needed":
                    status = "setup_needed"
                    error = verification.errors or "Lean setup is missing"
                    events.add("setup_needed", AgentRole.VERIFIER, error)
                    break
                errors.append(verification.errors or verification.output or "Lean rejected the proof")
            if status in {"success", "setup_needed"}:
                break
            if errors:
                events.add("repair_requested", AgentRole.REPAIR, "Sending Lean errors to repair agent", errors=errors[-3:])

    if status == "failed" and not error:
        error = "proof budget exhausted"
        events.add("budget_exhausted", AgentRole.ORCHESTRATOR, error)

    elapsed = int((perf_counter() - started) * 1000)
    events.add("trace_recorded", AgentRole.TRACE_RECORDER, "Trace ready for replay", elapsed_ms=elapsed)
    return ProofTrace(
        run_id=f"run-{uuid4().hex[:10]}",
        theorem=theorem,
        mode="real",
        provider=provider.name,
        model=provider.model,
        status=status,  # type: ignore[arg-type]
        events=events.events,
        attempts=attempts,
        final_proof=final_proof,
        error=error,
        elapsed_ms=elapsed,
    )


__all__ = ["ProofCandidate", "run_proof_graph", "langgraph_available"]
