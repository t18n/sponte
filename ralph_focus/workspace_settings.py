"""Per-workspace settings stored under ``workspace/.sponte/`` (not app state)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from config.defaults import SPONTE_DIR

SETTINGS_FILENAME = "settings.json"
DEFAULT_TRUNK_BRANCH = "sponte"
DEFAULT_WORKTREE_ROOT = ".sponte/worktrees"


@dataclass
class WorkspaceSettings:
    trunk_branch: str = DEFAULT_TRUNK_BRANCH
    worktree_root: str = DEFAULT_WORKTREE_ROOT

    def normalized_trunk(self) -> str:
        s = self.trunk_branch.strip()
        return s if s else DEFAULT_TRUNK_BRANCH

    def normalized_worktree_root(self) -> str:
        s = self.worktree_root.strip()
        return s if s else DEFAULT_WORKTREE_ROOT


def workspace_settings_path(root: Path) -> Path:
    return root / SPONTE_DIR / SETTINGS_FILENAME


def load_workspace_settings(root: Path) -> WorkspaceSettings:
    path = workspace_settings_path(root)
    if not path.is_file():
        return WorkspaceSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return WorkspaceSettings()
    if not isinstance(raw, dict):
        return WorkspaceSettings()
    trunk = raw.get("trunk_branch")
    worktree_root = raw.get("worktree_root")
    return WorkspaceSettings(
        trunk_branch=trunk.strip() if isinstance(trunk, str) and trunk.strip() else DEFAULT_TRUNK_BRANCH,
        worktree_root=(
            worktree_root.strip()
            if isinstance(worktree_root, str) and worktree_root.strip()
            else DEFAULT_WORKTREE_ROOT
        ),
    )


def save_workspace_settings(root: Path, settings: WorkspaceSettings) -> None:
    path = workspace_settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "trunk_branch": settings.normalized_trunk(),
        "worktree_root": settings.normalized_worktree_root(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "DEFAULT_TRUNK_BRANCH",
    "DEFAULT_WORKTREE_ROOT",
    "WorkspaceSettings",
    "load_workspace_settings",
    "save_workspace_settings",
    "workspace_settings_path",
]
