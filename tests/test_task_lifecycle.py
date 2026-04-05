"""Task lifecycle helpers (cancel/cleanup) — filesystem only."""

from __future__ import annotations

import json
from pathlib import Path

from ralph_focus.paths import sponte_job_task_dir, workspace_task_claim_lock_path
from ralph_focus.task_jobs import TaskJobStatus, write_task_job_status
from ralph_focus.task_lifecycle import cancel_task, task_cleanup


def test_cancel_unknown_task(tmp_path: Path) -> None:
    ok, msg = cancel_task(tmp_path, "nope-abcdef")
    assert not ok
    assert "unknown" in msg.lower()


def test_cleanup_repairs_missing_worktree_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ralph_focus.task_lifecycle.clear_resume",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "ralph_focus.task_lifecycle.clear_ralph_lock_matching_runner",
        lambda *a, **k: None,
    )
    tid = "demo-abcdef"
    job = sponte_job_task_dir(tmp_path, tid)
    job.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": tid,
        "rel_task": ".sponte/tasks/in-progress/x.md",
        "stage": "in-progress",
        "owning_session_id": "rap-deadbeef",
        "worktree_path": str(tmp_path / "missing-wt"),
        "branch": "ralph/wt-x",
    }
    (job / "status.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    n, notes = task_cleanup(tmp_path)
    assert n >= 1
    raw = json.loads((job / "status.json").read_text(encoding="utf-8"))
    assert raw.get("stage") == "backlog"
    assert raw.get("owning_session_id") == ""


def test_cancel_clears_workspace_claim_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("ralph_focus.task_lifecycle.clear_resume", lambda *a, **k: None)
    monkeypatch.setattr(
        "ralph_focus.task_lifecycle.clear_ralph_lock_matching_runner",
        lambda *a, **k: None,
    )
    monkeypatch.setattr("ralph_focus.task_lifecycle.git", lambda *a, **k: 0)
    monkeypatch.setattr("ralph_focus.task_lifecycle.worktree_registered", lambda *a, **k: False)

    tid = "ab-ffffff"
    write_task_job_status(
        tmp_path,
        TaskJobStatus(
            task_id=tid,
            rel_task=".sponte/tasks/in-progress/t.md",
            stage="in-progress",
            owning_session_id="rap-1111",
            worktree_path=str(tmp_path / "wt"),
            branch="b",
            task_title="t",
        ),
    )
    lock = workspace_task_claim_lock_path(tmp_path, tid)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{__import__('os').getpid()}\n", encoding="utf-8")

    ok, _msg = cancel_task(tmp_path, tid)
    assert ok
    assert not lock.is_file()
