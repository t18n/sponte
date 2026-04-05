"""Resolve ``Harness`` from workspace settings and CLI agent id."""

from __future__ import annotations

from pathlib import Path

from config.defaults import DEFAULT_AGENT
from ralph_focus.contracts import Harness, StrategyHarnessAdapter, get_harness
from ralph_focus.strategies.custom_cli import CustomCLIStrategy
from ralph_focus.workspace_settings import load_workspace_settings


def resolve_harness(primary: Path | None, agent_id: str) -> Harness:
    """
    Built-in ids use ``get_harness``; ``custom`` loads ``custom_harness`` from workspace settings.
    """
    aid = (agent_id or "").strip().lower()
    if aid == "custom":
        if primary is None:
            raise ValueError("custom harness requires a git workspace root")
        ws = load_workspace_settings(primary)
        ch = ws.custom_harness
        if ch is None or not ch.executable.strip():
            raise ValueError("custom harness not configured in .sponte/settings.json (custom_harness.executable)")
        return StrategyHarnessAdapter(CustomCLIStrategy(ch), _display_name="custom")
    return get_harness(aid if aid else DEFAULT_AGENT)


__all__ = ["resolve_harness"]
