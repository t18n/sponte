"""Detect live ``sponte agent`` sessions from ``ralph.lock`` files (best-effort)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from config.defaults import RUNTIME_DATA_SEGMENT, SPONTE_DIR
from ralph_focus.app_state_paths import sponte_state_base_dir
from ralph_focus.paths import use_workspace_runtime_data
from ralph_focus.workspaces_registry import load_known_workspaces


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        except OSError:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _locks_under_app_state_workspaces() -> list[Path]:
    root = sponte_state_base_dir() / "workspaces"
    if not root.is_dir():
        return []
    out: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        p = child / "ralph.lock"
        if p.is_file():
            out.append(p)
    return out


def _runtime_lock_path(primary: Path) -> Path:
    return primary / SPONTE_DIR / RUNTIME_DATA_SEGMENT / "ralph.lock"


def iter_ralph_lock_files() -> list[Path]:
    """All ``ralph.lock`` paths to inspect (deduped)."""
    seen: set[str] = set()
    out: list[Path] = []
    for p in _locks_under_app_state_workspaces():
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    for primary in load_known_workspaces():
        try:
            if use_workspace_runtime_data(primary):
                rp = _runtime_lock_path(primary)
                if rp.is_file():
                    key = str(rp.resolve())
                    if key not in seen:
                        seen.add(key)
                        out.append(rp)
        except OSError:
            continue
    return out


def _read_lock_file(path: Path) -> dict[str, object] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("schema_version") != 1:
        return None
    if not raw.get("runner_id"):
        return None
    return raw


def count_agent_sessions_from_locks() -> tuple[int, int, int]:
    """
    Return ``(live_sessions, stale_lock_files, total_lock_files)``.

    *live* means lock JSON parses and PID responds to a liveness probe.
    """
    paths = iter_ralph_lock_files()
    total = len(paths)
    stale = 0
    live = 0
    for path in paths:
        data = _read_lock_file(path)
        if data is None:
            stale += 1
            continue
        try:
            pid = int(data.get("pid", -1))
        except (TypeError, ValueError):
            stale += 1
            continue
        if _pid_alive(pid):
            live += 1
        else:
            stale += 1
    return live, stale, total


__all__ = [
    "count_agent_sessions_from_locks",
    "iter_ralph_lock_files",
]
