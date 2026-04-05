"""Detect whether a workspace has a usable ``.sponte/tasks`` layout."""

from __future__ import annotations

from pathlib import Path

from config.defaults import TASKS_DIR
from ralph_focus.tasks import priorities_file, priority_task_paths


def sponte_tasks_dir_exists(root: Path) -> bool:
    return (root / TASKS_DIR).is_dir()


def sponte_tasks_layout_valid(root: Path) -> bool:
    """True when tasks dir exists and priorities link to at least one path, or backlog has markdown tasks."""
    td = root / TASKS_DIR
    if not td.is_dir():
        return False
    pri = priorities_file(root)
    if pri.is_file() and priority_task_paths(pri, root):
        return True
    backlog = td / "backlog"
    if backlog.is_dir() and any(backlog.glob("*.md")):
        return True
    return False


__all__ = ["sponte_tasks_dir_exists", "sponte_tasks_layout_valid"]
