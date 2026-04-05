"""Resolve paths strictly under repo root (no traversal)."""

from __future__ import annotations

from pathlib import Path

from config.defaults import LEGACY_TASKS_DIR, TASKS_DIR

_LEGACY_TASKS_PREFIX = ".tasks/"


class PathGuardError(ValueError):
    pass


def ensure_repo_relative_path(repo_root: Path, user_path: str | Path, *, must_exist: bool = False) -> Path:
    """Resolve *user_path* under *repo_root*; reject escapes outside repo."""
    root = repo_root.resolve()
    raw = Path(user_path)
    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise PathGuardError(f"path escapes repository root: {user_path}") from e
    if must_exist and not candidate.exists():
        raise PathGuardError(f"path does not exist: {candidate}")
    return candidate


def validate_task_path_argument(repo_root: Path, arg: str) -> Path:
    """Normalize task file path to absolute under repo; must be under `.sponte/tasks/` (or legacy paths)."""
    p = ensure_repo_relative_path(repo_root, arg, must_exist=False)
    root = repo_root.resolve()
    rel = p.relative_to(root)
    rel_s = rel.as_posix()
    ok = (
        rel_s.startswith(f"{TASKS_DIR}/")
        or rel_s.startswith(_LEGACY_TASKS_PREFIX)
        or rel_s.startswith(f"{LEGACY_TASKS_DIR}/")
    )
    if not ok:
        raise PathGuardError(f"task file must be under {TASKS_DIR}/: {arg}")
    return p
