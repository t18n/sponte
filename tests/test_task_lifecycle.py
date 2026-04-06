"""Task lifecycle helpers (cancel/cleanup/resume)."""

from __future__ import annotations

import json
from pathlib import Path

from ralph_focus.paths import sponte_job_task_dir, workspace_task_claim_lock_path
from ralph_focus.resume import ResumeState, load_resume, write_resume
from ralph_focus.task_jobs import (
    SessionJobStatus,
    TaskJobStatus,
    read_session_job_status,
    read_task_job_status,
    write_session_job_status,
    write_task_job_status,
)
from ralph_focus.task_lifecycle import (
    cancel_task,
    migrate_task_job_ids,
    prepare_task_resume,
    task_cleanup,
)
from config.defaults import TASKS_DIR
from ralph_focus.tasks import task_id_from_resolved_path


def test_cancel_unknown_task(tmp_path: Path) -> None:
    ok, msg = cancel_task(tmp_path, "nope-abcdef")
    assert not ok
    assert "unknown" in msg.lower()


def test_cleanup_repairs_missing_worktree_status_and_restores_task_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ralph_focus.task_lifecycle.clear_resume",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "ralph_focus.task_lifecycle.clear_ralph_lock_matching_runner",
        lambda *a, **k: None,
    )

    def fake_git(repo: Path, *args: str):
        if args and args[0] == "mv":
            src = repo / args[1]
            dest = repo / args[2]
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
        return 0, "", ""

    monkeypatch.setattr("ralph_focus.task_lifecycle.git", fake_git)
    tid = "demo-abcdef"
    job = sponte_job_task_dir(tmp_path, tid)
    job.mkdir(parents=True, exist_ok=True)
    task_path = tmp_path / ".sponte" / "tasks" / "in-progress" / "x.md"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text("- [ ] orphaned\n", encoding="utf-8")
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
    assert not task_path.exists()
    assert (tmp_path / ".sponte" / "tasks" / "backlog" / "x.md").is_file()


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
    write_session_job_status(
        tmp_path,
        SessionJobStatus(
            session_id="rap-1111",
            workspace_root=str(tmp_path.resolve()),
            active_task_id=tid,
            rel_task=".sponte/tasks/in-progress/t.md",
            phase="IMPLEMENT",
            worktree_path=str(tmp_path / "wt"),
            branch="b",
        ),
    )
    lock = workspace_task_claim_lock_path(tmp_path, tid)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{__import__('os').getpid()}\n", encoding="utf-8")

    ok, _msg = cancel_task(tmp_path, tid)
    assert ok
    assert not lock.is_file()
    session = read_session_job_status(tmp_path, "rap-1111")
    assert session is not None
    assert session.active_task_id == ""


def test_prepare_task_resume_carries_previous_state_and_clears_old_session(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    monkeypatch.setattr("ralph_focus.task_lifecycle.worktree_registered", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "ralph_focus.task_lifecycle.clear_ralph_lock_matching_runner",
        lambda *a, **k: None,
    )
    wt = tmp_path / "wt"
    wt.mkdir()
    task_rel = f"{TASKS_DIR}/in-progress/demo.md"
    task_path = tmp_path / task_rel
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text("task: Demo\n\n- [ ] resume\n", encoding="utf-8")

    tid = "demo-abcdef"
    old_session = "rap-old1234"
    write_task_job_status(
        tmp_path,
        TaskJobStatus(
            task_id=tid,
            rel_task=task_rel,
            stage="in-progress",
            owning_session_id=old_session,
            worktree_path=str(wt),
            branch="ralph/wt-demo",
            task_title="Demo",
        ),
    )
    write_session_job_status(
        tmp_path,
        SessionJobStatus(
            session_id=old_session,
            workspace_root=str(tmp_path.resolve()),
            active_task_id=tid,
            rel_task=task_rel,
            phase="VERIFY",
            worktree_path=str(wt),
            branch="ralph/wt-demo",
        ),
    )
    write_resume(
        tmp_path,
        ResumeState(
            primary=str(tmp_path.resolve()),
            phase="VERIFY",
            logf=str(tmp_path / "old.log"),
            wt_path=str(wt),
            branch="ralph/wt-demo",
            main_ref="main",
            rel_task=task_rel,
            plan_rel=str(tmp_path / "plan.md"),
            implement_next=3,
            improve_i=2,
            improve_j=1,
            conflict_next=4,
            cycles_done=5,
            max_cycles="8",
            agent_kind="claude",
            plan_model="saved-plan",
            agent_model="saved-exec",
            session_deadline_epoch="123",
            no_progress_loops=2,
            resume_runner_id=old_session,
            task_id=tid,
        ),
        runner_id=old_session,
    )

    new_session, err = prepare_task_resume(tmp_path, tid)

    assert err == ""
    assert new_session is not None
    resumed = load_resume(tmp_path, runner_id=new_session)
    assert resumed is not None
    assert resumed.phase == "VERIFY"
    assert resumed.plan_model == "saved-plan"
    assert resumed.agent_model == "saved-exec"
    assert resumed.implement_next == 3
    assert resumed.conflict_next == 4
    assert resumed.task_id == tid
    old_status = read_session_job_status(tmp_path, old_session)
    assert old_status is not None
    assert old_status.active_task_id == ""


def test_cleanup_prunes_tasks_lock_missing_paths(tmp_path: Path) -> None:
    from ralph_focus.tasks_lock_registry import read_tasks_lock_paths, write_tasks_lock_paths

    ghost = tmp_path / "nowhere" / "gone.md"
    write_tasks_lock_paths(tmp_path, {ghost})
    n, notes = task_cleanup(tmp_path)
    assert n >= 1
    assert len(read_tasks_lock_paths(tmp_path)) == 0
    assert any("tasks.lock" in x for x in notes)


def test_cleanup_prunes_deferred_completed_job_dir(tmp_path: Path) -> None:
    tid = "t-cleanuppending01"
    job = sponte_job_task_dir(tmp_path, tid)
    job.mkdir(parents=True, exist_ok=True)
    (job / "status.json").write_text(
        json.dumps(
            {
                "task_id": tid,
                "rel_task": ".sponte/tasks/missing-never-created.md",
                "stage": "completed",
                "completed": True,
                "cleanup_pending": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    n, notes = task_cleanup(tmp_path)
    assert n >= 1
    assert any("cleanup_pending" in x for x in notes)
    assert not job.is_dir()


def test_cleanup_skips_deferred_prune_when_task_file_remains(tmp_path: Path) -> None:
    task_rel = ".sponte/tasks/still-here.md"
    p = tmp_path / task_rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("- [x] done\n", encoding="utf-8")
    tid = "t-stillhere01"
    job = sponte_job_task_dir(tmp_path, tid)
    job.mkdir(parents=True, exist_ok=True)
    (job / "status.json").write_text(
        json.dumps(
            {
                "task_id": tid,
                "rel_task": task_rel,
                "stage": "completed",
                "completed": True,
                "cleanup_pending": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    task_cleanup(tmp_path)
    assert job.is_dir()


def test_migrate_task_job_ids_rewrites_folder_and_session_pointer(tmp_path: Path) -> None:
    task_rel = ".sponte/tasks/flat.md"
    task_path = tmp_path / task_rel
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text("# t\n\n- [ ] x\n", encoding="utf-8")
    expected = task_id_from_resolved_path(task_path.resolve())
    legacy_id = "legacy-slug-abc123"
    write_task_job_status(
        tmp_path,
        TaskJobStatus(
            task_id=legacy_id,
            rel_task=task_rel,
            stage="backlog",
            task_title="Flat",
        ),
    )
    old_job = sponte_job_task_dir(tmp_path, legacy_id)
    assert old_job.is_dir()

    write_session_job_status(
        tmp_path,
        SessionJobStatus(
            session_id="rap-migrate01",
            workspace_root=str(tmp_path.resolve()),
            active_task_id=legacy_id,
            rel_task=task_rel,
            phase="PLAN",
            worktree_path=str(tmp_path / "wt"),
            branch="b",
        ),
    )
    m, mnotes = migrate_task_job_ids(tmp_path)
    assert m == 1
    assert any("migrated" in x for x in mnotes)
    assert not old_job.is_dir()
    new_job = sponte_job_task_dir(tmp_path, expected)
    assert new_job.is_dir()
    st = read_task_job_status(tmp_path, expected)
    assert st is not None
    assert st.task_id == expected
    sess = read_session_job_status(tmp_path, "rap-migrate01")
    assert sess is not None
    assert sess.active_task_id == expected
