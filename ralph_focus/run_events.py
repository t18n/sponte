"""Shared run-monitor event types without contract/strategy import cycles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class RunWatchdog:
    stall_timeout_sec: float | None = None
    total_runtime_timeout_sec: float | None = None


@dataclass(frozen=True)
class RunEvent:
    kind: str
    text: str = ""
    usage_delta: dict[str, int] = field(default_factory=dict)
    estimated: bool = False
    reason: str = ""


RunEventCallback = Callable[[RunEvent], None]
