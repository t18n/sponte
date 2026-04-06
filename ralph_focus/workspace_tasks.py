"""Detect whether a workspace has a usable ``.sponte/tasks`` layout."""

from __future__ import annotations

from pathlib import Path

from config.defaults import TASKS_DIR


def sponte_tasks_dir_exists(root: Path) -> bool:
    return (root / TASKS_DIR).is_dir()


def sponte_tasks_layout_valid(root: Path) -> bool:
    """True when ``.sponte/tasks`` exists (flat or staged markdown files)."""
    return (root / TASKS_DIR).is_dir()


__all__ = ["sponte_tasks_dir_exists", "sponte_tasks_layout_valid"]
