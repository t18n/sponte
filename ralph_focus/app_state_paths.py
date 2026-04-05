"""Cross-workspace runtime state (Sponte app state), outside the repository tree."""

from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path


def _default_state_base() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser() / "sponte"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "sponte"
    return Path.home() / ".local" / "state" / "sponte"


def sponte_state_base_dir() -> Path:
    """Root directory for Sponte state on this machine.

    Override with ``SPONTE_STATE_DIR`` for tests or custom layouts.
    """
    override = os.environ.get("SPONTE_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _default_state_base().expanduser().resolve()


def workspace_state_slug(workspace_root: Path) -> str:
    """Stable directory name for *workspace_root* (resolved path)."""
    key = str(workspace_root.resolve())
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def workspace_runtime_root(workspace_root: Path) -> Path:
    """Per-workspace directory under app state (locks, resume, plans, session lock, …)."""
    return sponte_state_base_dir() / "workspaces" / workspace_state_slug(workspace_root)


__all__ = [
    "sponte_state_base_dir",
    "workspace_runtime_root",
    "workspace_state_slug",
]
