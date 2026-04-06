"""Central defaults for Ralph CLI. Override via environment variables where noted."""

from __future__ import annotations

import os

# --- Session / loop ---
# When the session has no wall-clock limit (default; --unlimited; or --once), cap consecutive
# failed cycle retries (each failure still has resume state) to avoid spinning forever.
MAX_RESUME_ERRORS_UNLIMITED_SESSION: int = int(
    os.environ.get("RALPH_AUTO_FOCUS_MAX_RESUME_ERRORS_UNLIMITED", "50")
)

# --- Agent rounds ---
IMPLEMENT_ROUNDS_MAX: int = int(os.environ.get("RALPH_AUTO_FOCUS_IMPLEMENT_ROUNDS_MAX", "15"))
IMPROVE_IMPLEMENT_MAX: int = int(os.environ.get("RALPH_AUTO_FOCUS_IMPROVE_IMPLEMENT_MAX", "5"))
CONFLICT_ROUNDS_MAX: int = int(os.environ.get("RALPH_AUTO_FOCUS_CONFLICT_ROUNDS_MAX", "5"))

# --- Models (env mirrors old bash) ---
DEFAULT_PLAN_MODEL: str = os.environ.get("RALPH_AUTO_FOCUS_PLAN_MODEL", "auto")
DEFAULT_EXECUTE_MODEL: str = os.environ.get("RALPH_AUTO_FOCUS_AGENT_MODEL", "auto")

# --- Agent backend ---
DEFAULT_AGENT: str = os.environ.get("RALPH_AUTO_FOCUS_AGENT", "cursor")

# --- Workspace-owned paths (relative to repository / primary checkout root) ---
SPONTE_DIR: str = ".sponte"
SPONTE_TASKS_SEGMENT: str = "tasks"
SPONTE_WORKTREES_SEGMENT: str = "worktrees"
GUARDRAILS_BASENAME: str = "guardrails.md"
PROGRESS_BASENAME: str = "progress.md"

TASKS_DIR: str = f"{SPONTE_DIR}/{SPONTE_TASKS_SEGMENT}"
WORKTREE_BASE_DIR: str = f"{SPONTE_DIR}/{SPONTE_WORKTREES_SEGMENT}"
SPONTE_TASKS_PATH: str = TASKS_DIR
SPONTE_WORKTREES_PATH: str = WORKTREE_BASE_DIR
SPONTE_GUARDRAILS_PATH: str = f"{SPONTE_DIR}/{GUARDRAILS_BASENAME}"
SPONTE_PROGRESS_PATH: str = f"{SPONTE_DIR}/{PROGRESS_BASENAME}"

# Legacy repo-relative paths (resume migration, merge precheck ignores)
LEGACY_RALPH_DATA_DIR: str = ".agents/ralph/data"
LEGACY_TASKS_DIR: str = ".agents/tasks"

# --- Runtime under app state (see ralph_focus.app_state_paths); not a repo-relative path ---
# Per-session logs/resume live under ``runners/<id>/agent/``. Legacy installs used ``auto-focus/``;
# resume load still falls back there (see ``ralph_focus.resume``).
AGENT_SESSION_SUBDIR: str = "agent"
LEGACY_AGENT_SESSION_SUBDIR: str = "auto-focus"
NEXT_TASK_FILENAME: str = "auto-focus-next-task.txt"

# --- Resume schema ---
RESUME_SCHEMA_VERSION: int = 3

# --- Same-repo concurrent auto-focus (cooperative locks under data/locks/) ---
MERGE_LOCK_TIMEOUT_SEC: float = float(os.environ.get("RALPH_MERGE_LOCK_TIMEOUT_SEC", "900"))
SELECTION_LOCK_TIMEOUT_SEC: float = float(os.environ.get("RALPH_SELECTION_LOCK_TIMEOUT_SEC", "120"))
AGENT_PICK_LOCK_TIMEOUT_SEC: float = float(os.environ.get("RALPH_AGENT_PICK_LOCK_TIMEOUT_SEC", "900"))

# --- Preflight ---
REQUIRE_GH_AUTH: bool = os.environ.get("RALPH_REQUIRE_GH", "").lower() in ("1", "true", "yes")

# --- Git ---
GIT_IDENTITY_NAME: str = "ralph-auto-focus"
GIT_IDENTITY_EMAIL: str = "ralph-auto-focus@localhost"

# --- Progress ---
DEFAULT_PROGRESS: str = "on"  # off | on | full
STREAM_STALL_TIMEOUT_SEC: float = float(
    os.environ.get("RALPH_AUTO_FOCUS_STREAM_STALL_TIMEOUT_SEC", "120")
)
TOTAL_RUNTIME_TIMEOUT_SEC: float = float(
    os.environ.get("RALPH_AUTO_FOCUS_TOTAL_RUNTIME_TIMEOUT_SEC", "1800")
)

# --- Codex CLI ---
CODEX_EXECUTABLE: str = os.environ.get("RALPH_CODEX_BIN", "codex")

# --- Factory Droid CLI (`droid exec`) ---
DROID_EXECUTABLE: str = os.environ.get("RALPH_DROID_BIN", "droid")
# Autonomy tier for headless runs; Ralph needs edits + local git (no push): default medium.
DROID_AUTO_LEVEL: str = os.environ.get("RALPH_DROID_AUTO", "medium").strip().lower()


def _derived_warn_threshold(rotate_threshold: int) -> str:
    if rotate_threshold <= 0:
        return "0"
    return str(max(1, int(rotate_threshold * 0.875)))


# --- Token rotation / gutter detection ---
ROTATE_THRESHOLD_TOKENS: int = int(os.environ.get("RALPH_AUTO_FOCUS_ROTATE_THRESHOLD_TOKENS", "80000"))
ROTATE_WARN_THRESHOLD_TOKENS: int = int(
    os.environ.get(
        "RALPH_AUTO_FOCUS_ROTATE_WARN_THRESHOLD_TOKENS",
        _derived_warn_threshold(ROTATE_THRESHOLD_TOKENS),
    )
)
NO_PROGRESS_LOOPS_MAX: int = int(os.environ.get("RALPH_AUTO_FOCUS_NO_PROGRESS_LOOPS_MAX", "3"))
