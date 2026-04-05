"""PID-stamped cooperative locks under `.agents/ralph/data/locks/`.

Creation uses ``O_CREAT|O_EXCL`` so only one process can take a given lock path;
stale locks (dead owner PID) are removed and acquisition retried.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


class LockHeldError(Exception):
    def __init__(self, path: Path, pid: str) -> None:
        self.path = path
        self.pid = pid
        super().__init__(f"lock held by PID {pid} ({path})")


def _lock_file_bytes(pid: int) -> bytes:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return f"{pid}\n{ts}\n".encode("utf-8")


def _read_holder_pid(lock_path: Path) -> str | None:
    if not lock_path.is_file():
        return None
    try:
        first = lock_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except OSError:
        return None
    return first if first else None


def _try_remove_stale_lock(lock_path: Path) -> bool:
    """If the lock is missing, corrupt, or owned by a dead PID, remove it. Returns True if removed."""
    holder = _read_holder_pid(lock_path)
    if holder is None:
        lock_path.unlink(missing_ok=True)
        return True
    if not holder.isdigit():
        lock_path.unlink(missing_ok=True)
        return True
    try:
        os.kill(int(holder), 0)
    except ProcessLookupError:
        lock_path.unlink(missing_ok=True)
        return True
    except PermissionError:
        pass
    return False


def acquire_lock(lock_path: Path) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    my_pid = os.getpid()
    while True:
        try:
            fd = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
            try:
                os.write(fd, _lock_file_bytes(my_pid))
            finally:
                os.close(fd)
            return
        except FileExistsError:
            if _try_remove_stale_lock(lock_path):
                continue
            holder = _read_holder_pid(lock_path) or "?"
            raise LockHeldError(lock_path, holder) from None


def release_lock(lock_path: Path) -> None:
    if not lock_path.is_file():
        return
    try:
        first = lock_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except OSError:
        return
    if first == str(os.getpid()):
        lock_path.unlink(missing_ok=True)
