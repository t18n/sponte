"""Task cancel, cleanup, and resume preparation (workspace ``.sponte`` is source of truth)."""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from config.defaults import GIT_IDENTITY_EMAIL, GIT_IDENTITY_NAME, RESUME_SCHEMA_VERSION, TASKS_DIR
from ralph_focus.git_ops import git, worktree_registered
from ralph_focus.lockfile import release_lock
from ralph_focus.paths import (
    auto_focus_logs_dir,
    sponte_jobs_sessions_root,
    sponte_jobs_tasks_root,
    workspace_task_claim_lock_path,
)
from ralph_focus.resume import ResumeState, clear_resume, load_resume, write_resume
from ralph_focus.ralph_session_lock import clear_ralph_lock_matching_runner
from ralph_focus.lockfile import _try_remove_stale_lock
from ralph_focus.task_jobs import (
    SessionJobStatus,
    TaskJobStatus,
    read_task_job_status,
    write_session_job_status,
    write_task_job_status,
)
from ralph_focus.tasks import concrete_task_rel, task_stage, task_with_stage
from ralph_focus.workspace_analytics import bump_summary
from ralph_focus.workspace_resolve import resolve_trunk_branch_ref


def _unlink_quiet(p: Path) -> None:
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def cancel_task(repo: Path, task_id: str) -> tuple[bool, str]:
    st = read_task_job_status(repo, task_id)
    if st is None:
        return False, f"unknown task_id: {task_id}"
    if st.stage == "completed":
        return False, "task is already completed (use git history, not cancel)"
    if st.stage == "backlog" and not (st.owning_session_id or "").strip():
        return False, "task is not actively owned"

    sess = (st.owning_session_id or "").strip()
    if sess:
        clear_resume(repo, runner_id=sess)
        clear_ralph_lock_matching_runner(repo, sess)

    clp = workspace_task_claim_lock_path(repo, task_id)
    release_lock(clp)
    _unlink_quiet(clp)

    wt = Path(st.worktree_path) if st.worktree_path.strip() else None
    br = (st.branch or "").strip()
    if wt is not None and wt.is_dir() and worktree_registered(repo, wt):
        git(repo, "worktree", "remove", "-f", str(wt))
    if br:
        git(repo, "branch", "-D", br)

    new_rel = (st.rel_task or "").strip()
    if new_rel:
        abs_p = repo / new_rel
        if abs_p.is_file() and task_stage(new_rel) == "in-progress":
            dest_rel = task_with_stage(new_rel, "backlog")
            (repo / dest_rel).parent.mkdir(parents=True, exist_ok=True)
            git(repo, "mv", new_rel, dest_rel)
            git(
                repo,
                "-c",
                f"user.name={GIT_IDENTITY_NAME}",
                "-c",
                f"user.email={GIT_IDENTITY_EMAIL}",
                "commit",
                "-m",
                f"chore(tasks): cancel {task_id} -> backlog",
            )
            new_rel = dest_rel

    write_task_job_status(
        repo,
        TaskJobStatus(
            task_id=task_id,
            rel_task=new_rel,
            stage="backlog",
            owning_session_id="",
            worktree_path="",
            branch="",
            task_title=st.task_title,
        ),
    )
    try:
        bump_summary(repo, tasks_cancelled=1)
    except OSError:
        pass
    return True, "cancelled"


def cancel_all_active_tasks(repo: Path) -> tuple[int, list[str]]:
    n = 0
    errors: list[str] = []
    root = sponte_jobs_tasks_root(repo)
    if not root.is_dir():
        return 0, errors
    for status_path in root.glob("*/status.json"):
        try:
            raw = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(raw, dict):
            continue
        tid = str(raw.get("task_id", "")).strip()
        stage = str(raw.get("stage", "")).strip()
        owner = str(raw.get("owning_session_id", "")).strip()
        if not tid:
            continue
        if stage in ("in-progress", "review-required") or owner:
            ok, msg = cancel_task(repo, tid)
            if ok:
                n += 1
            else:
                errors.append(f"{tid}: {msg}")
    return n, errors


def task_cleanup(repo: Path) -> tuple[int, list[str]]:
    """Conservative repair: orphan claim locks, stale job rows (missing worktree)."""
    repairs = 0
    notes: list[str] = []
    lock_root = repo / ".sponte" / "locks" / "tasks"
    if lock_root.is_dir():
        for lp in lock_root.glob("*.lock"):
            if _try_remove_stale_lock(lp):
                repairs += 1
                notes.append(f"removed stale lock {lp.name}")

    root = sponte_jobs_tasks_root(repo)
    if root.is_dir():
        for status_path in root.glob("*/status.json"):
            try:
                raw = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            if not isinstance(raw, dict):
                continue
            tid = str(raw.get("task_id", "")).strip()
            stage = str(raw.get("stage", "")).strip()
            wt_s = str(raw.get("worktree_path", "")).strip()
            owner = str(raw.get("owning_session_id", "")).strip()
            if not tid:
                continue
            wt = Path(wt_s) if wt_s else None
            if stage == "in-progress" and owner and (wt is None or not wt.is_dir()):
                if owner:
                    clear_resume(repo, runner_id=owner)
                    clear_ralph_lock_matching_runner(repo, owner)
                release_lock(workspace_task_claim_lock_path(repo, tid))
                _unlink_quiet(workspace_task_claim_lock_path(repo, tid))
                rel = str(raw.get("rel_task", "")).strip()
                write_task_job_status(
                    repo,
                    TaskJobStatus(
                        task_id=tid,
                        rel_task=rel,
                        stage="backlog",
                        owning_session_id="",
                        worktree_path="",
                        branch="",
                        task_title=str(raw.get("task_title", "")),
                    ),
                )
                repairs += 1
                notes.append(f"repaired orphan in-progress {tid}")
    if repairs:
        try:
            bump_summary(repo, cleanup_repairs=repairs)
        except OSError:
            pass
    return repairs, notes


def prepare_task_resume(repo: Path, task_id: str) -> tuple[str | None, str]:
    """
    Create resume state under a **new** session id for an existing worktree.
    Returns ``(new_session_id, "")`` or ``(None, error_message)``.
    """
    st = read_task_job_status(repo, task_id)
    if st is None:
        return None, f"unknown task_id: {task_id}"
    if st.stage not in ("in-progress", "review-required"):
        return None, "task is not resumable (expected in-progress or review-required)"
    wt = Path(st.worktree_path)
    if not wt.is_dir() or not worktree_registered(repo, wt):
        return None, "worktree missing or not registered; try task-cleanup"
    rel_task = (st.rel_task or "").strip()
    if not rel_task or not (wt / rel_task).is_file():
        return None, "task file missing in worktree"

    old_sess = (st.owning_session_id or "").strip()
    if old_sess:
        clear_resume(repo, runner_id=old_sess)
        clear_ralph_lock_matching_runner(repo, old_sess)

    new_rid = f"rap-{secrets.token_hex(4)}"
    prev = load_resume(repo, runner_id=old_sess) if old_sess else None
    logf = auto_focus_logs_dir(repo, runner_id=new_rid) / f"run-{int(time.time())}.log"
    logf.parent.mkdir(parents=True, exist_ok=True)
    logf.write_text("", encoding="utf-8")

    main_ref = prev.main_ref if prev and prev.main_ref.strip() else resolve_trunk_branch_ref(repo, cli_override=None)
    br_name = (st.branch or "").strip() or (prev.branch if prev else "")
    plan_rel = prev.plan_rel if prev and prev.plan_rel.strip() else ""
    if not plan_rel:
        from ralph_focus.paths import plan_file_for_task

        plan_rel = plan_file_for_task(repo, Path(rel_task).stem).resolve().as_posix()

    phase = "IMPLEMENT"
    if prev and prev.phase.strip():
        phase = prev.phase.strip()

    rs = ResumeState(
        schema_version=RESUME_SCHEMA_VERSION,
        primary=str(repo.resolve()),
        phase=phase,
        logf=str(logf),
        wt_path=str(wt),
        branch=br_name,
        main_ref=main_ref,
        rel_task=concrete_task_rel(repo, rel_task),
        plan_rel=plan_rel,
        implement_next=prev.implement_next if prev else 1,
        improve_i=prev.improve_i if prev else 1,
        improve_j=prev.improve_j if prev else 0,
        conflict_next=prev.conflict_next if prev else 1,
        cycles_done=prev.cycles_done if prev else 0,
        max_cycles=prev.max_cycles if prev else "",
        task_arg="",
        agent_kind=prev.agent_kind if prev and prev.agent_kind.strip() else "cursor",
        plan_model=prev.plan_model if prev else "",
        agent_model=prev.agent_model if prev else "",
        allow_agent_pick="false",
        session_deadline_epoch=prev.session_deadline_epoch if prev else "",
        total_tokens=0,
        no_progress_loops=prev.no_progress_loops if prev else 0,
        token_warning_emitted="false",
        resume_runner_id=new_rid,
        task_id=task_id,
    )
    write_resume(repo, rs, runner_id=new_rid)

    write_task_job_status(
        repo,
        TaskJobStatus(
            task_id=task_id,
            rel_task=rs.rel_task,
            stage=st.stage,
            owning_session_id=new_rid,
            worktree_path=str(wt),
            branch=br_name,
            task_title=st.task_title,
        ),
    )
    write_session_job_status(
        repo,
        SessionJobStatus(
            session_id=new_rid,
            workspace_root=str(repo.resolve()),
            active_task_id=task_id,
            rel_task=rs.rel_task,
            phase=phase,
            worktree_path=str(wt),
            branch=br_name,
        ),
    )
    return new_rid, ""


def iter_session_status_files(repo: Path) -> list[Path]:
    root = sponte_jobs_sessions_root(repo)
    if not root.is_dir():
        return []
    return sorted(root.glob("*/status.json"))


def iter_task_status_files(repo: Path) -> list[Path]:
    root = sponte_jobs_tasks_root(repo)
    if not root.is_dir():
        return []
    return sorted(root.glob("*/status.json"))


def list_backlog_tasks(repo: Path) -> list[Path]:
    return sorted((repo / TASKS_DIR / "backlog").rglob("*.md"))


__all__ = [
    "cancel_all_active_tasks",
    "cancel_task",
    "iter_session_status_files",
    "iter_task_status_files",
    "list_backlog_tasks",
    "prepare_task_resume",
    "task_cleanup",
]
