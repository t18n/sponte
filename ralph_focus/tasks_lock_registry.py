"""Newline-separated absolute task paths under ``.sponte/locks/tasks.lock`` (repo-local)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def tasks_lock_path(repo: Path) -> Path:
    from ralph_focus.paths import workspace_sponte_locks_dir

    return workspace_sponte_locks_dir(repo) / "tasks.lock"


def read_tasks_lock_paths(repo: Path) -> set[Path]:
    p = tasks_lock_path(repo)
    if not p.is_file():
        return set()
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    out: set[Path] = set()
    for line in raw.splitlines():
        s = line.strip()
        if s:
            try:
                out.add(Path(s).expanduser().resolve())
            except OSError:
                continue
    return out


def _write_paths_atomic(path: Path, paths: set[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = sorted({str(p) for p in paths})
    body = "\n".join(lines) + ("\n" if lines else "")
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".tasks.lock.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_tasks_lock_paths(repo: Path, paths: set[Path]) -> None:
    _write_paths_atomic(tasks_lock_path(repo), paths)


def tasks_lock_append(repo: Path, task_abs: Path) -> None:
    resolved = task_abs.expanduser().resolve()
    current = read_tasks_lock_paths(repo)
    current.add(resolved)
    write_tasks_lock_paths(repo, current)


def tasks_lock_remove(repo: Path, task_abs: Path) -> None:
    resolved = task_abs.expanduser().resolve()
    current = read_tasks_lock_paths(repo)
    current.discard(resolved)
    write_tasks_lock_paths(repo, current)


def tasks_lock_prune_missing(repo: Path) -> tuple[int, list[Path]]:
    """Drop lock lines whose files no longer exist. Returns (removed_count, removed_paths)."""
    current = read_tasks_lock_paths(repo)
    stale = [p for p in current if not p.is_file()]
    if not stale:
        return 0, []
    for p in stale:
        current.discard(p)
    write_tasks_lock_paths(repo, current)
    return len(stale), stale


def path_is_tasks_locked(repo: Path, task_abs: Path) -> bool:
    try:
        return task_abs.expanduser().resolve() in read_tasks_lock_paths(repo)
    except OSError:
        return False
