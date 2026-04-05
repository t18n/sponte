"""Cooperative locks for parallel auto-focus (same repo, multiple terminals).

Lock ordering (avoid deadlock): never acquire selection/agent-pick locks while holding
``merge-into-<branch>.lock``. Typical flow: selection.lock (brief) -> per-task lock ->
... work ... -> merge-into-main.lock (or master/…) for checkout on primary + merge +
worktree teardown (only one Ralph merges into that branch at a time).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config.defaults import MERGE_LOCK_TIMEOUT_SEC
from ralph_focus.lockfile import LockHeldError, acquire_lock, release_lock
from ralph_focus.paths import merge_into_branch_lock_path


class LockWaitTimeoutError(Exception):
    def __init__(self, path: Path, timeout_sec: float) -> None:
        self.path = path
        self.timeout_sec = timeout_sec
        super().__init__(f"timed out after {timeout_sec}s waiting for lock ({path})")


def acquire_lock_blocking(lock_path: Path, *, timeout_sec: float, poll_sec: float = 0.12) -> None:
    deadline = time.monotonic() + timeout_sec
    while True:
        try:
            acquire_lock(lock_path)
            return
        except LockHeldError:
            if time.monotonic() >= deadline:
                raise LockWaitTimeoutError(lock_path, timeout_sec) from None
            time.sleep(poll_sec)


def try_acquire_task_lock(lock_path: Path) -> bool:
    try:
        acquire_lock(lock_path)
    except LockHeldError:
        return False
    return True


def release_lock_if_mine(lock_path: Path) -> None:
    release_lock(lock_path)


@contextmanager
def merge_phase_locked(
    primary: Path,
    merge_target_branch: str,
    *,
    timeout_sec: float | None = None,
) -> Iterator[None]:
    """Exclusive section for ``git checkout <branch>`` + merge + primary cleanup on that branch."""
    lim = MERGE_LOCK_TIMEOUT_SEC if timeout_sec is None else timeout_sec
    mp = merge_into_branch_lock_path(primary, merge_target_branch)
    acquire_lock_blocking(mp, timeout_sec=lim)
    try:
        yield
    finally:
        release_lock(mp)
