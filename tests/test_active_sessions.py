"""Tests for ralph.lock live-session helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _valid_lock_payload(*, pid: int | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "runner_id": "rap-test",
        "pid": os.getpid() if pid is None else pid,
        "primary": "/tmp",
        "session_cycle": 1,
        "resuming_this_cycle": False,
        "updated_at": "2026-04-07T12:00:00Z",
        "resume_hint": "sponte session-resume rap-test",
    }


def test_count_live_sessions_for_primary_no_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ralph_focus import active_sessions as ac

    lock = tmp_path / "ralph.lock"
    monkeypatch.setattr(ac, "ralph_lock_path", lambda _p: lock)

    from ralph_focus.active_sessions import count_live_sessions_for_primary

    assert count_live_sessions_for_primary(tmp_path) == 0


def test_count_live_sessions_for_primary_live(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import active_sessions as ac

    lock = tmp_path / "ralph.lock"
    lock.write_text(json.dumps(_valid_lock_payload()) + "\n", encoding="utf-8")
    monkeypatch.setattr(ac, "ralph_lock_path", lambda _p: lock)

    from ralph_focus.active_sessions import count_live_sessions_for_primary

    assert count_live_sessions_for_primary(tmp_path) == 1


def test_count_live_sessions_for_primary_stale_pid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import active_sessions as ac

    lock = tmp_path / "ralph.lock"
    lock.write_text(json.dumps(_valid_lock_payload(pid=999_999_999)) + "\n", encoding="utf-8")
    monkeypatch.setattr(ac, "ralph_lock_path", lambda _p: lock)

    from ralph_focus.active_sessions import count_live_sessions_for_primary

    assert count_live_sessions_for_primary(tmp_path) == 0


@pytest.mark.parametrize(
    "contents",
    [
        "{not json",
        json.dumps({"schema_version": 2, "runner_id": "rap-test", "pid": os.getpid()}),
        json.dumps({"schema_version": 1, "pid": os.getpid()}),
        json.dumps({"schema_version": 1, "runner_id": "rap-test"}),
        json.dumps({"schema_version": 1, "runner_id": "rap-test", "pid": "not-a-pid"}),
    ],
)
def test_count_live_sessions_for_primary_ignores_invalid_lock_payloads(
    contents: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ralph_focus import active_sessions as ac

    lock = tmp_path / "ralph.lock"
    lock.write_text(contents + "\n", encoding="utf-8")
    monkeypatch.setattr(ac, "ralph_lock_path", lambda _p: lock)

    from ralph_focus.active_sessions import count_live_sessions_for_primary

    assert count_live_sessions_for_primary(tmp_path) == 0
