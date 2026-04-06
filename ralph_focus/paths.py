"""Path API: workspace `.sponte/*` vs cross-workspace app state."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from config.defaults import (
    AGENT_SESSION_SUBDIR,
    GUARDRAILS_BASENAME,
    LEGACY_AGENT_SESSION_SUBDIR,
    LEGACY_RALPH_DATA_DIR,
    NEXT_TASK_FILENAME,
    PROGRESS_BASENAME,
    RUNTIME_DATA_SEGMENT,
    SPONTE_DIR,
    WORKTREE_BASE_DIR,
)
from ralph_focus.app_state_paths import workspace_runtime_root
from ralph_focus.workspace_settings import load_workspace_settings


def workspace_sponte_dir(root: Path) -> Path:
    return root / SPONTE_DIR


def guardrails_markdown_path(root: Path) -> Path:
    return root / SPONTE_DIR / GUARDRAILS_BASENAME


def progress_markdown_path(root: Path) -> Path:
    return root / SPONTE_DIR / PROGRESS_BASENAME


def use_workspace_runtime_data(workspace_root: Path) -> bool:
    """True when logs, resume, plans, locks, etc. live under ``.sponte/<runtime>/`` instead of app state."""
    flag = os.environ.get("SPONTE_RUNTIME_DATA_IN_WORKSPACE", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return load_workspace_settings(workspace_root).runtime_data.strip().lower() == "workspace"


def ralph_data_dir(workspace_root: Path) -> Path:
    """Runtime data directory: Sponte app state by default, or workspace-local ``.sponte/<runtime>/``."""
    if use_workspace_runtime_data(workspace_root):
        return workspace_sponte_dir(workspace_root) / RUNTIME_DATA_SEGMENT
    return workspace_runtime_root(workspace_root)


def ralph_lock_path(primary: Path) -> Path:
    """Session marker for the active auto-focus run (under ``ralph_data_dir``)."""
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


def agent_session_data_dir(primary: Path, runner_id: str) -> Path:
    """Per-session data under ``runners/<id>/agent/`` (logs, resume, handoff)."""
    return ralph_data_dir(primary) / "runners" / sanitize_runner_segment(runner_id) / AGENT_SESSION_SUBDIR


def legacy_agent_session_data_dir(primary: Path, runner_id: str) -> Path:
    """Pre-rename layout: ``runners/<id>/auto-focus/`` (resume read fallback only)."""
    return ralph_data_dir(primary) / "runners" / sanitize_runner_segment(runner_id) / LEGACY_AGENT_SESSION_SUBDIR


def auto_focus_data_dir(primary: Path, runner_id: str) -> Path:
    """Alias for :func:`agent_session_data_dir` (historical name)."""
    return agent_session_data_dir(primary, runner_id)


def auto_focus_logs_dir(root: Path, *, runner_id: str = "default") -> Path:
    return auto_focus_data_dir(root, runner_id) / "logs"


def resume_file(primary: Path, *, runner_id: str = "default") -> Path:
    """Path for **writing** resume state (always under ``agent/``)."""
    return agent_session_data_dir(primary, runner_id) / "resume.state"


def resume_file_legacy(primary: Path, *, runner_id: str = "default") -> Path:
    """Legacy resume path under ``auto-focus/`` (read fallback)."""
    return legacy_agent_session_data_dir(primary, runner_id) / "resume.state"


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
    """Plan files live under ``ralph_data_dir``; *workspace_root* must be the primary checkout root."""
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
    from ralph_focus.workspace_settings import load_workspace_settings

    configured = Path(load_workspace_settings(primary).normalized_worktree_root())
    if configured.is_absolute():
        return configured
    return primary / configured


def sponte_jobs_root(root: Path) -> Path:
    """Repo-local job index under ``.sponte/jobs/`` (tasks + sessions)."""
    return workspace_sponte_dir(root) / "jobs"


def sponte_jobs_tasks_root(root: Path) -> Path:
    return sponte_jobs_root(root) / "tasks"


def sponte_jobs_sessions_root(root: Path) -> Path:
    return sponte_jobs_root(root) / "sessions"


def sanitize_job_segment(segment: str) -> str:
    """Filesystem-safe single path segment for job ids (defense in depth)."""
    s = segment.strip()
    if not s:
        return "unnamed"
    if re.fullmatch(r"[a-zA-Z0-9._-]{1,120}", s):
        return s[:120]
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    return f"h-{h}"


def sponte_job_task_dir(root: Path, task_id: str) -> Path:
    return sponte_jobs_tasks_root(root) / sanitize_job_segment(task_id)


def sponte_job_session_dir(root: Path, session_id: str) -> Path:
    return sponte_jobs_sessions_root(root) / sanitize_runner_segment(session_id)


def sponte_job_session_task_dir(root: Path, session_id: str, task_id: str) -> Path:
    return sponte_job_session_dir(root, session_id) / "tasks" / sanitize_job_segment(task_id)


def workspace_sponte_locks_dir(root: Path) -> Path:
    """Cooperative locks under ``.sponte/locks/`` (workspace-owned ownership)."""
    return workspace_sponte_dir(root) / "locks"


def workspace_task_claim_lock_path(root: Path, task_id: str) -> Path:
    """Exclusive claim lock for a task id (prevents duplicate active claims)."""
    return workspace_sponte_locks_dir(root) / "tasks" / f"{sanitize_job_segment(task_id)}.lock"


def naming_reply_file(workspace_root: Path, task_id: str) -> Path:
    """Where the task naming prompt writes one JSON object (under ``ralph_data_dir``)."""
    return ralph_data_dir(workspace_root) / "naming" / f"{sanitize_job_segment(task_id)}.json"


def sponte_task_work_tmp_dir(root: Path, task_id: str) -> Path:
    """Ignored runtime dir for Sponte-owned helper docs (``_tmp``)."""
    return workspace_sponte_dir(root) / "tasks" / "_tmp" / sanitize_job_segment(task_id)


def sponte_tracked_task_artifacts_dir(root: Path, task_id: str) -> Path:
    """Tracked (when gitignored) archive root for merged task artifacts."""
    return workspace_sponte_dir(root) / "artifacts" / "tasks" / sanitize_job_segment(task_id)
