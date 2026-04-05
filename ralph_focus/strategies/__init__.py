"""Agent backends."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ralph_focus.strategies.amp import AmpStrategy
from ralph_focus.strategies.claude import ClaudeStrategy
from ralph_focus.strategies.codex import CodexStrategy
from ralph_focus.strategies.cursor import CursorStrategy
from ralph_focus.strategies.droid import DroidStrategy
from ralph_focus.strategies.oz import OzStrategy


@runtime_checkable
class AgentStrategy(Protocol):
    id: str

    def check_available(self) -> list[str]:
        """Return list of human-readable errors if unavailable."""
        ...

    def run(
        self,
        cwd: Path,
        model: str,
        prompt: str,
        log_file: Path,
        *,
        use_stream_json: bool,
        tee: bool,
        metrics_out: Path | None,
    ) -> tuple[int, dict[str, int]]:
        ...


def get_strategy(name: str) -> AgentStrategy:
    n = name.lower().strip()
    if n == "cursor":
        return CursorStrategy()
    if n == "claude":
        return ClaudeStrategy()
    if n == "codex":
        return CodexStrategy()
    if n == "droid":
        return DroidStrategy()
    if n in ("oz", "warp"):
        return OzStrategy()
    if n == "amp" or n == "ampcode":
        return AmpStrategy()
    raise ValueError(f"unknown agent: {name!r} (use cursor|claude|codex|droid|oz|warp|amp)")


__all__ = [
    "AgentStrategy",
    "AmpStrategy",
    "ClaudeStrategy",
    "CodexStrategy",
    "CursorStrategy",
    "DroidStrategy",
    "OzStrategy",
    "get_strategy",
]
