from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Status = Literal["success", "failed", "setup_needed", "provider_error", "timeout", "replay"]
Mode = Literal["real", "replay"]
SearchStrategy = Literal["beam", "mcts"]


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    DECOMPOSER = "decomposer"
    TACTIC = "tactic_agent"
    REPAIR = "repair_agent"
    VERIFIER = "verifier"
    ASSEMBLER = "assembler"
    TRACE_RECORDER = "trace_recorder"


class Benchmark(BaseModel):
    id: str
    title: str
    suite: str
    difficulty: str
    imports: str = ""
    statement: str
    source: str
    expected_tactics: List[str] = Field(default_factory=list)
    replay_trace: Optional[str] = None
    lean_project_dir: Optional[str] = None
    description: str = ""


class LeanResult(BaseModel):
    success: bool
    status: Status
    output: str = ""
    errors: str = ""
    command: List[str] = Field(default_factory=list)
    elapsed_ms: int = 0


class ProofCandidate(BaseModel):
    proof: str
    rationale: str = ""


class ProofAttempt(BaseModel):
    iteration: int
    agent: AgentRole
    proof: str
    rationale: str = ""
    verification: LeanResult


class TraceEvent(BaseModel):
    index: int
    kind: str
    agent: AgentRole
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ProofTrace(BaseModel):
    run_id: str
    theorem: Benchmark
    mode: Mode
    provider: str
    model: str
    status: Status
    events: List[TraceEvent] = Field(default_factory=list)
    attempts: List[ProofAttempt] = Field(default_factory=list)
    final_proof: Optional[str] = None
    error: str = ""
    elapsed_ms: int = 0
    token_usage: Dict[str, int] = Field(default_factory=dict)


class RunRequest(BaseModel):
    theorem_id: str
    suite: str = "smoke"
    mode: Mode = "real"
    provider: str = "openai"
    model: str = ""
    max_attempts: int = 3
    beam_width: int = 1
    search_strategy: SearchStrategy = "beam"
    mcts_iterations: int = 12
    replay_trace: Optional[str] = None

    def __init__(self, **data: Any) -> None:
        if "max_attempts" in data:
            data["max_attempts"] = max(1, min(int(data["max_attempts"]), 8))
        if "beam_width" in data:
            data["beam_width"] = max(1, min(int(data["beam_width"]), 5))
        if "mcts_iterations" in data:
            data["mcts_iterations"] = max(1, min(int(data["mcts_iterations"]), 40))
        super().__init__(**data)


def model_to_dict(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def model_to_json(model: BaseModel) -> str:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json()
    return model.json()
