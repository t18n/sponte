"""Tests for ``.sponte/jobs/`` task/session metadata."""

from __future__ import annotations

from pathlib import Path

from config.defaults import TASKS_DIR


def test_task_job_status_roundtrip(tmp_path: Path) -> None:
    from ralph_focus.task_jobs import TaskJobStatus, read_task_job_status, write_task_job_status

    root = tmp_path / "repo"
    rec = TaskJobStatus(
        task_id="demo-abcdef",
        rel_task=f"{TASKS_DIR}/in-progress/demo.md",
        owning_session_id="rap-1111",
        worktree_path=str(root / "wt"),
        branch="ralph/wt-demo-abcdef",
        task_title="Demo",
    )
    write_task_job_status(root, rec)
    loaded = read_task_job_status(root, "demo-abcdef")
    assert loaded is not None
    assert loaded.task_id == "demo-abcdef"
    assert loaded.owning_session_id == "rap-1111"
    assert loaded.branch == "ralph/wt-demo-abcdef"
