"""Tests for orphan worktree recovery via persisted resume state."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.defaults import TASKS_DIR
from ralph_focus.paths import plan_file_for_task
from ralph_focus.resume import (
    ResumeState,
    list_recoverable_resumes,
    resolve_runner_for_task_id,
    resolve_runner_for_worktree,
    write_resume,
)


def test_list_recoverable_resumes_scans_runner_segments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    wt = tmp_path / ".sponte" / "worktrees" / "job-1"
    wt.mkdir(parents=True)
    st = ResumeState(
        primary=str(tmp_path.resolve()),
        logf=str(tmp_path / "run.log"),
        wt_path=str(wt.resolve()),
        rel_task=f"{TASKS_DIR}/in-progress/example.md",
        plan_rel=str(plan_file_for_task(tmp_path, "example")),
        resume_runner_id="lane-a",
    )
    write_resume(tmp_path, st, runner_id="lane-a")

    rows = list_recoverable_resumes(tmp_path)

    assert len(rows) == 1
    rid, loaded = rows[0]
    assert rid == "lane-a"
    assert loaded is not None
    assert Path(loaded.wt_path).resolve() == wt.resolve()


def test_list_recoverable_uses_directory_segment_when_runner_id_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    wt = tmp_path / "wt"
    wt.mkdir()
    st = ResumeState(
        primary=str(tmp_path.resolve()),
        logf=str(tmp_path / "run.log"),
        wt_path=str(wt.resolve()),
        rel_task=f"{TASKS_DIR}/in-progress/example.md",
        plan_rel=str(plan_file_for_task(tmp_path, "example")),
        resume_runner_id="",
    )
    write_resume(tmp_path, st, runner_id="lane-b")

    rows = list_recoverable_resumes(tmp_path)
    assert len(rows) == 1
    rid, _ = rows[0]
    assert rid == "lane-b"


def test_resolve_runner_for_worktree_matches_normalized_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    wt = tmp_path / ".sponte" / "worktrees" / "x"
    wt.mkdir(parents=True)
    st = ResumeState(
        primary=str(tmp_path.resolve()),
        logf=str(tmp_path / "run.log"),
        wt_path=str(wt.resolve()),
        rel_task=f"{TASKS_DIR}/in-progress/example.md",
        plan_rel=str(plan_file_for_task(tmp_path, "example")),
        resume_runner_id="gen-1",
    )
    write_resume(tmp_path, st, runner_id="gen-1")

    resolved = resolve_runner_for_worktree(tmp_path, wt)

    assert resolved is not None
    rid, state = resolved
    assert rid == "gen-1"
    assert state.phase == st.phase


def test_resolve_runner_for_worktree_returns_none_when_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    wt = tmp_path / "missing-wt"
    assert resolve_runner_for_worktree(tmp_path, wt) is None


def test_resolve_runner_for_worktree_none_when_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    wt = tmp_path / "shared-wt"
    wt.mkdir()
    shared = str(wt.resolve())
    for rid in ("lane-x", "lane-y"):
        st = ResumeState(
            primary=str(tmp_path.resolve()),
            logf=str(tmp_path / f"{rid}.log"),
            wt_path=shared,
            rel_task=f"{TASKS_DIR}/in-progress/example.md",
            plan_rel=str(plan_file_for_task(tmp_path, "example")),
            resume_runner_id=rid,
        )
        write_resume(tmp_path, st, runner_id=rid)

    assert resolve_runner_for_worktree(tmp_path, wt) is None


def test_resolve_runner_for_task_id_matches_unique_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    wt = tmp_path / ".sponte" / "worktrees" / "job-1"
    wt.mkdir(parents=True)
    st = ResumeState(
        primary=str(tmp_path.resolve()),
        logf=str(tmp_path / "run.log"),
        wt_path=str(wt.resolve()),
        rel_task=f"{TASKS_DIR}/in-progress/example.md",
        plan_rel=str(plan_file_for_task(tmp_path, "example")),
        resume_runner_id="gen-1",
        task_id="demo-abc123",
    )
    write_resume(tmp_path, st, runner_id="gen-1")

    resolved = resolve_runner_for_task_id(tmp_path, "demo-abc123")

    assert resolved is not None
    rid, state = resolved
    assert rid == "gen-1"
    assert state.task_id == "demo-abc123"


def test_resolve_runner_for_task_id_returns_none_when_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    assert resolve_runner_for_task_id(tmp_path, "missing-id") is None


def test_resolve_runner_for_task_id_none_when_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    wt = tmp_path / "wt"
    wt.mkdir()
    shared_tid = "same-task-id"
    for rid in ("lane-x", "lane-y"):
        st = ResumeState(
            primary=str(tmp_path.resolve()),
            logf=str(tmp_path / f"{rid}.log"),
            wt_path=str(wt.resolve()),
            rel_task=f"{TASKS_DIR}/in-progress/example.md",
            plan_rel=str(plan_file_for_task(tmp_path, "example")),
            resume_runner_id=rid,
            task_id=shared_tid,
        )
        write_resume(tmp_path, st, runner_id=rid)

    assert resolve_runner_for_task_id(tmp_path, shared_tid) is None
