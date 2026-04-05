"""Path API: workspace `.sponte/*` vs cross-workspace app state."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from config.defaults import (
    AUTO_FOCUS_SUBDIR,
    GUARDRAILS_BASENAME,
    LEGACY_RALPH_DATA_DIR,
    NEXT_TASK_FILENAME,
    PROGRESS_BASENAME,
    SPONTE_DIR,
    WORKTREE_BASE_DIR,
)
from ralph_focus.app_state_paths import workspace_runtime_root


def workspace_sponte_dir(root: Path) -> Path:
    return root / SPONTE_DIR


def guardrails_markdown_path(root: Path) -> Path:
    return root / SPONTE_DIR / GUARDRAILS_BASENAME


def progress_markdown_path(root: Path) -> Path:
    return root / SPONTE_DIR / PROGRESS_BASENAME


def ralph_data_dir(workspace_root: Path) -> Path:
    """Runtime data directory for this workspace (under Sponte app state, not in the repo)."""
    return workspace_runtime_root(workspace_root)


def ralph_lock_path(primary: Path) -> Path:
    """Session marker for the active auto-focus run (app state, gitignored only by omission from repo)."""
    return ralph_data_dir(primary) / "ralph.lock"


def sanitize_runner_segment(runner_id: str) -> str:
    """Filesystem-safe directory name for a runner id."""
    s = runner_id.strip()
    if not s:
        return "unnamed"
    if re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", s):
        return s[:80]
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    return f"h-{h}"


def auto_focus_data_dir(primary: Path, runner_id: str) -> Path:
    """Resume + logs under `runners/<id>/auto-focus/`."""
    return ralph_data_dir(primary) / "runners" / sanitize_runner_segment(runner_id) / AUTO_FOCUS_SUBDIR


def auto_focus_logs_dir(root: Path, *, runner_id: str = "default") -> Path:
    return auto_focus_data_dir(root, runner_id) / "logs"


def resume_file(primary: Path, *, runner_id: str = "default") -> Path:
    return auto_focus_data_dir(primary, runner_id) / "resume.state"


def rotation_handoff_file(primary: Path, *, runner_id: str = "default") -> Path:
    return auto_focus_data_dir(primary, runner_id) / "rotation-handoff.md"


def locks_dir(primary: Path) -> Path:
    return ralph_data_dir(primary) / "locks"


def sanitize_branch_lock_segment(branch_ref: str) -> str:
    """Filesystem-safe segment from a branch name (e.g. ``main`` -> ``main``)."""
    s = branch_ref.strip().replace("\\", "/").split("/")[-1]
    if not s:
        return "unnamed"
    if re.fullmatch(r"[a-zA-Z0-9._-]{1,64}", s):
        return s[:64]
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    return f"h-{h}"


def merge_into_branch_lock_path(primary: Path, branch_ref: str) -> Path:
    """Serialize merges and primary checkout into this local branch (e.g. ``main``)."""
    seg = sanitize_branch_lock_segment(branch_ref)
    return locks_dir(primary) / f"merge-into-{seg}.lock"


def selection_lock_path(primary: Path) -> Path:
    return locks_dir(primary) / "selection.lock"


def agent_pick_lock_path(primary: Path) -> Path:
    return locks_dir(primary) / "agent-pick.lock"


def task_lock_path_for_rel(primary: Path, task_rel_posix: str) -> Path:
    h = hashlib.sha256(task_rel_posix.encode("utf-8")).hexdigest()[:24]
    return locks_dir(primary) / "tasks" / f"{h}.lock"


def next_task_file(primary: Path) -> Path:
    return ralph_data_dir(primary) / NEXT_TASK_FILENAME


def plans_dir(workspace_root: Path) -> Path:
    """Plan files live under app state; *workspace_root* must be the primary checkout root."""
    return ralph_data_dir(workspace_root) / "plans"


def plan_file_for_task(workspace_root: Path, task_stem: str) -> Path:
    return plans_dir(workspace_root) / f"{task_stem}.md"


def base_sha_file(workspace_root: Path) -> Path:
    return ralph_data_dir(workspace_root) / "auto-focus-base-sha"


def base_task_file(workspace_root: Path) -> Path:
    return ralph_data_dir(workspace_root) / "auto-focus-base-task"


def legacy_base_sha_file(workspace_root: Path) -> Path:
    return workspace_root / LEGACY_RALPH_DATA_DIR / "auto-focus-base-sha"


def legacy_base_task_file(workspace_root: Path) -> Path:
    return workspace_root / LEGACY_RALPH_DATA_DIR / "auto-focus-base-task"


def readable_base_sha_file(workspace_root: Path) -> Path:
    current = base_sha_file(workspace_root)
    legacy = legacy_base_sha_file(workspace_root)
    if current.exists() or not legacy.exists():
        return current
    return legacy


def readable_base_task_file(workspace_root: Path) -> Path:
    current = base_task_file(workspace_root)
    legacy = legacy_base_task_file(workspace_root)
    if current.exists() or not legacy.exists():
        return current
    return legacy


def worktrees_base(primary: Path) -> Path:
    return primary / WORKTREE_BASE_DIR
