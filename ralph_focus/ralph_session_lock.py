"""Persist current agent session id to Sponte app state ``ralph.lock`` (per workspace).

Several concurrent ``sponte agent`` processes overwrite the same file; use
``--runner-id`` / ``RALPH_RUNNER_ID`` per lane for **new** sessions when running multiple terminals.
"""

from __future__ import annotations

import json
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ralph_focus.paths import ralph_lock_path
from ralph_focus.resume import load_resume

SCHEMA_VERSION = 1


def _coerce_lock_payload(raw: dict[str, Any]) -> dict[str, Any] | None:
    ver = raw.get("schema_version")
    if ver != SCHEMA_VERSION:
        return None
    if not raw.get("runner_id"):
        return None
    return raw


def write_ralph_lock(
    primary: Path,
    *,
    runner_id: str,
    session_cycle: int,
    resuming_this_cycle: bool,
) -> None:
    path = ralph_lock_path(primary)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "runner_id": runner_id,
        "pid": os.getpid(),
        "primary": str(primary.resolve()),
        "session_cycle": session_cycle,
        "resuming_this_cycle": resuming_this_cycle,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resume_hint": (
            "sponte agent --resume "
            f"{shlex.quote(runner_id)} --plan-model auto --execute-model auto"
        ),
    }
    data = json.dumps(payload, indent=2) + "\n"
    tmp = path.with_name(f".ralph.lock.{os.getpid()}.tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def read_ralph_lock(primary: Path) -> dict[str, Any] | None:
    path = ralph_lock_path(primary)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    return _coerce_lock_payload(raw)


def clear_ralph_lock_matching_runner(primary: Path, runner_id: str) -> None:
    data = read_ralph_lock(primary)
    if data is None:
        return
    if data.get("runner_id") != runner_id:
        return
    ralph_lock_path(primary).unlink(missing_ok=True)


def finalize_ralph_lock_if_session_idle(primary: Path, runner_id: str) -> None:
    """Remove lock when this process has no resume left for this runner (clean end)."""
    if load_resume(primary, runner_id=runner_id) is not None:
        return
    data = read_ralph_lock(primary)
    if data is None:
        return
    if data.get("runner_id") != runner_id:
        return
    try:
        lock_pid = int(data.get("pid", -1))
    except (TypeError, ValueError):
        return
    if lock_pid != os.getpid():
        return
    ralph_lock_path(primary).unlink(missing_ok=True)
