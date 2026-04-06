"""Repo-local ``.sponte/locks/merge.lock`` — single-line owning ``session_id`` during merge."""

from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


def merge_lock_path(repo: Path) -> Path:
    from ralph_focus.paths import workspace_sponte_locks_dir

    return workspace_sponte_locks_dir(repo) / "merge.lock"


def read_merge_lock_holder(repo: Path) -> str:
    p = merge_lock_path(repo)
    if not p.is_file() or p.stat().st_size == 0:
        return ""
    try:
        line = p.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
    except OSError:
        return ""
    return line


@dataclass(frozen=True)
class MergeBackoffSettings:
    enabled: bool = True
    base_ms: float = 500.0
    max_ms: float = 10_000.0
    jitter: bool = True

    @classmethod
    def from_json(cls, raw: object) -> MergeBackoffSettings:
        if raw is None or raw is False:
            return cls(enabled=False)
        if raw is True:
            return cls()
        if not isinstance(raw, dict):
            return cls()
        en = raw.get("enabled", True)
        base = raw.get("base_ms", 500)
        mx = raw.get("max_ms", 10_000)
        jit = raw.get("jitter", True)
        try:
            base_f = float(base)
            max_f = float(mx)
        except (TypeError, ValueError):
            return cls()
        return cls(
            enabled=bool(en) if isinstance(en, bool) else str(en).lower() in ("1", "true", "yes"),
            base_ms=max(1.0, base_f),
            max_ms=max(base_f, max_f),
            jitter=bool(jit) if isinstance(jit, bool) else str(jit).lower() in ("1", "true", "yes"),
        )


def acquire_merge_lock(repo: Path, session_id: str) -> bool:
    """Create merge.lock exclusively. Returns False if another session holds it."""
    sid = session_id.strip()
    if not sid:
        return False
    p = merge_lock_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, (sid + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False


class RepoMergeLockTimeoutError(Exception):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"timed out waiting for repo merge.lock ({path})")


@contextmanager
def repo_merge_lock_held(
    repo: Path,
    session_id: str,
    backoff: MergeBackoffSettings,
    timeout_sec: float,
) -> Iterator[None]:
    deadline = time.monotonic() + timeout_sec
    if not acquire_merge_lock_blocking(
        repo,
        session_id,
        backoff,
        deadline_monotonic=deadline,
    ):
        raise RepoMergeLockTimeoutError(merge_lock_path(repo))
    try:
        yield
    finally:
        release_merge_lock(repo, session_id)


def release_merge_lock(repo: Path, session_id: str) -> None:
    """Remove merge.lock only when the first line matches *session_id*."""
    sid = session_id.strip()
    if not sid:
        return
    if read_merge_lock_holder(repo) != sid:
        return
    try:
        merge_lock_path(repo).unlink(missing_ok=True)
    except OSError:
        pass


def acquire_merge_lock_blocking(
    repo: Path,
    session_id: str,
    settings: MergeBackoffSettings,
    *,
    deadline_monotonic: float | None = None,
) -> bool:
    """
    Try to take merge.lock with exponential backoff until *deadline_monotonic* (``time.monotonic()``).

    When settings.enabled is False, single non-blocking attempt.
    """
    if acquire_merge_lock(repo, session_id):
        return True
    if not settings.enabled:
        return False
    delay_ms = settings.base_ms
    while True:
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            return False
        sleep_s = min(settings.max_ms, delay_ms) / 1000.0
        if settings.jitter and sleep_s > 0:
            sleep_s *= 0.5 + random.random() * 0.5
        time.sleep(sleep_s)
        if acquire_merge_lock(repo, session_id):
            return True
        delay_ms = min(settings.max_ms, delay_ms * 2)
