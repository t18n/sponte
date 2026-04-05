"""Aggregate session metrics across cycles and agent steps."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def _usage_total_tokens(usage: dict[str, int]) -> int:
    explicit_total = next(
        (
            int(v)
            for k, v in usage.items()
            if isinstance(v, (int, float)) and "total" in k.lower() and ("token" in k.lower() or k.lower() == "total")
        ),
        None,
    )
    if explicit_total is not None:
        return explicit_total
    filtered_total = sum(
        int(v)
        for k, v in usage.items()
        if isinstance(v, (int, float)) and ("token" in k.lower() or k.lower() in ("input", "output", "prompt", "completion", "cache"))
    )
    if filtered_total > 0:
        return filtered_total
    if len(usage) == 1:
        only_value = next(iter(usage.values()))
        if isinstance(only_value, (int, float)):
            return int(only_value)
    return 0


def _usage_rotation_tokens(usage: dict[str, int]) -> int:
    component_total = sum(
        int(v)
        for k, v in usage.items()
        if isinstance(v, (int, float))
        and ("token" in k.lower() or k.lower() in ("input", "output", "prompt", "completion"))
        and "cache" not in k.lower()
        and "total" not in k.lower()
    )
    if component_total > 0:
        return component_total
    return _usage_total_tokens(usage)


@dataclass
class SessionStats:
    started_monotonic: float = field(default_factory=time.monotonic)
    started_wall: float = field(default_factory=time.time)
    cycles_completed: int = 0
    resume_retries: int = 0
    exit_reason: str = ""
    step_wall_seconds: float = 0.0
    token_totals: dict[str, int] = field(default_factory=dict)
    total_token_count: int = 0
    rotation_token_count: int = 0
    agent_steps: int = 0
    merge_conflict_rounds: int = 0

    def add_tokens(self, usage: dict[str, int]) -> None:
        for k, v in usage.items():
            self.token_totals[k] = self.token_totals.get(k, 0) + int(v)
        self.total_token_count += _usage_total_tokens(usage)
        self.rotation_token_count += _usage_rotation_tokens(usage)

    def add_step_wall(self, seconds: float) -> None:
        self.step_wall_seconds += seconds
        self.agent_steps += 1

    def total_tokens(self) -> int:
        return self.total_token_count

    def rotation_tokens(self) -> int:
        return self.rotation_token_count
