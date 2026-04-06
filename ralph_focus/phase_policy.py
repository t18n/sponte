"""Phase ownership and agent/model selection rules."""

from __future__ import annotations

PLANNER_PHASES = frozenset({"PLAN", "IMPROVE", "IMPROVE_REVIEW", "CONSISTENCY_REVIEW", "VERIFY"})
EXECUTOR_PHASES = frozenset(
    {
        "IMPLEMENT",
        "IMPROVE_EXECUTE",
        "CONSISTENCY_EXECUTE",
        "WRAP",
        "MERGE_CONFLICT",
        "PRIMARY_PREMERGE",
    }
)
NON_AGENT_PHASES = frozenset({"MERGE"})


def phase_uses_agent(phase: str) -> bool:
    return phase not in NON_AGENT_PHASES


def phase_model_for(phase: str, *, plan_model: str, execute_model: str) -> str:
    if phase in PLANNER_PHASES:
        return plan_model
    if phase in EXECUTOR_PHASES:
        return execute_model
    if phase in NON_AGENT_PHASES:
        return ""
    raise ValueError(f"unknown Ralph phase: {phase}")
