"""Detect whether a workspace has a usable ``.sponte/tasks`` layout."""

from __future__ import annotations

from pathlib import Path

from config.defaults import TASKS_DIR
from ralph_focus.tasks import priorities_file, priority_task_paths


def sponte_tasks_dir_exists(root: Path) -> bool:
    return (root / TASKS_DIR).is_dir()


def sponte_tasks_layout_valid(root: Path) -> bool:
    """True when tasks dir exists and has the expected planner-owned structure."""
    td = root / TASKS_DIR
    if not td.is_dir():
        return False
    backlog = td / "backlog"
    in_progress = td / "in-progress"
    review = td / "review-required"
    completed = td / "completed"
    if not backlog.is_dir() or not in_progress.is_dir() or not completed.is_dir():
        return False
    if not review.is_dir():
        review.mkdir(parents=True, exist_ok=True)
    pri = priorities_file(root)
    if pri.is_file():
        return True
    return False


__all__ = ["sponte_tasks_dir_exists", "sponte_tasks_layout_valid"]
