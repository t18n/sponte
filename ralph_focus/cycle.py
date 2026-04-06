"""One-ticket cycle: worktree, phases, merge to default branch (no push)."""

from __future__ import annotations

import json
import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from config.commands import (
    git_add_all_args,
    git_checkout_branch_args,
    git_commit_no_edit_args,
    git_diff_cached_quiet_args,
    git_merge_abort_args,
    git_merge_feature_args,
    git_status_porcelain_args,
    git_verify_ref_args,
    verify_commands_markdown,
)
from config.defaults import (
    AGENT_PICK_LOCK_TIMEOUT_SEC,
    CONFLICT_ROUNDS_MAX,
    MERGE_LOCK_TIMEOUT_SEC,
    GIT_IDENTITY_EMAIL,
    GIT_IDENTITY_NAME,
    IMPLEMENT_ROUNDS_MAX,
    IMPROVE_IMPLEMENT_MAX,
    NO_PROGRESS_LOOPS_MAX,
    RESUME_SCHEMA_VERSION,
    ROTATE_THRESHOLD_TOKENS,
    ROTATE_WARN_THRESHOLD_TOKENS,
    STREAM_STALL_TIMEOUT_SEC,
    TASKS_DIR,
    TOTAL_RUNTIME_TIMEOUT_SEC,
)
from ralph_focus.contracts import FailureContext, Harness, RunRequest
from ralph_focus.harness_resolve import resolve_harness
from ralph_focus.failure_detection import FailureKind, ProgressSnapshot
from ralph_focus.phase_policy import PLANNER_PHASES, phase_model_for
from ralph_focus.git_message import truncate_subject
from ralph_focus.git_ops import git, worktree_registered
from ralph_focus.workspace_resolve import resolve_trunk_branch_ref
from ralph_focus.lockfile import release_lock
from ralph_focus.parallel_locks import (
    LockWaitTimeoutError,
    acquire_lock_blocking,
    merge_phase_locked,
    try_acquire_task_lock,
)
from ralph_focus.repo_merge_lock import RepoMergeLockTimeoutError, repo_merge_lock_held
from ralph_focus.paths import (
    agent_pick_lock_path,
    auto_focus_logs_dir,
    base_sha_file,
    base_task_file,
    naming_reply_file,
    next_task_file,
    plan_file_for_task,
    plans_dir,
    ralph_data_dir,
    readable_base_sha_file,
    rotation_handoff_file,
    sanitize_job_segment,
    sponte_job_task_dir,
    sponte_tracked_task_artifacts_dir,
    worktrees_base,
    workspace_task_claim_lock_path,
)
from ralph_focus.primary_precheck import (
    PrimaryPrecheckKind,
    is_branch_merged_into,
    primary_merge_precheck_state,
)
from ralph_focus.progress import (
    banner,
    max_agent_steps,
    merge_precheck_failed,
    merge_precheck_warning,
    phase_bar,
    step_done,
    task_block,
)
from ralph_focus.prompts import render_prompt
from ralph_focus.run_events import RunWatchdog
from ralph_focus.resume import ResumeState, clear_resume, load_resume, update_resume_runtime_state, write_resume
from ralph_focus.session_stats import SessionStats, _usage_rotation_tokens
from ralph_focus.task_jobs import (
    SessionJobStatus,
    TaskJobStatus,
    append_task_job_artifact,
    init_task_job_artifacts,
    read_task_job_status,
    touch_session_job_folder,
    write_session_job_status,
    write_task_job_status,
)
from ralph_focus.task_lifecycle import (
    _clear_session_active_task,
    _restore_task_to_backlog,
    format_claimed_tasks_snapshot,
)
from ralph_focus.token_rotation import TokenRotationPolicy, derive_warn_threshold
from ralph_focus.workspace_analytics import bump_summary, emit_lifecycle_event
from ralph_focus.tasks import (
    concrete_task_rel,
    count_checklist,
    format_pending_backlog_for_prompt,
    naming_content_hash,
    normalize_task_path,
    normalize_task_rel,
    pending_selectable_task_paths,
    task_has_pending,
    task_id_from_resolved_path,
    task_label,
)
from ralph_focus.tasks_lock_registry import (
    path_is_tasks_locked,
    tasks_lock_append,
    tasks_lock_prune_missing,
    tasks_lock_remove,
)
from ralph_focus.workspace_settings import load_workspace_settings

ProgressMode = Literal["off", "on", "full"]

_COUNTED_AGENT_PHASES = frozenset({
    "PLAN",
    "IMPLEMENT",
    "IMPROVE_REVIEW",
    "IMPROVE_EXECUTE",
    "WRAP",
    "VERIFY",
})


@dataclass
class _PhaseBudgetCtx:
    wt_path: Path
    rel_task: str
    logf: Path
    br_name: str
    main_ref: str
    plan_rel: str
    implement_next: int
    improve_i: int
    improve_j: int
    conflict_next: int


def phase_uses_plan_model(phase: str) -> bool:
    return phase in PLANNER_PHASES


def derive_warn_threshold_tokens(rotate_threshold: int) -> int:
    return derive_warn_threshold(rotate_threshold)


def should_rotate_after_usage(usage: dict[str, int], rotate_threshold: int) -> bool:
    if rotate_threshold <= 0:
        return False
    total = _usage_rotation_tokens(usage)
    return total >= rotate_threshold


def _append_phase_log(logf: Path, name: str) -> None:
    try:
        logf.parent.mkdir(parents=True, exist_ok=True)
        with logf.open("a", encoding="utf-8") as f:
            f.write("\n")
            f.write("#" * 64 + "\n")
            f.write(f"# PHASE: {name}\n")
            f.write("#" * 64 + "\n")
    except OSError:
        # Low-disk and other local I/O failures should not crash the cycle while logging.
        return


def worktree_clean(wt: Path) -> bool:
    code, out, _ = git(wt, "status", "--porcelain")
    return code == 0 and not out.strip()


def _append_diagnostic_log(logf: Path, title: str, detail: str) -> None:
    try:
        logf.parent.mkdir(parents=True, exist_ok=True)
        with logf.open("a", encoding="utf-8") as f:
            f.write("\n")
            f.write("#" * 64 + "\n")
            f.write(f"# {title}\n")
            f.write("#" * 64 + "\n")
            if detail.strip():
                f.write(detail.rstrip() + "\n")
    except OSError:
        # Best-effort only; callers should keep handling the original failure.
        return


def _failure_detail(logf: Path, inline_detail: str = "") -> str:
    return "\n".join(part for part in (inline_detail.strip(), _log_tail(logf)) if part).strip()


def _fatal_resume_error(cfg: AutoFocusConfig, detail: str) -> int:
    cfg.last_failure_kind = FailureKind.FATAL
    cfg.last_failure_detail = detail
    return 1


def _commit_worktree_pending_if_dirty(wt_path: Path, logf: Path, subject_suffix: str) -> bool:
    """
    If the worktree has uncommitted changes, stage all and commit with Ralph git identity.
    Used after agent phases that are allowed to edit files without an explicit commit step.
    """
    code, out, err = git(wt_path, *git_status_porcelain_args())
    if code != 0:
        _append_diagnostic_log(logf, "AUTO_COMMIT: git status failed in worktree", err or "")
        return False
    if not out.strip():
        return True

    _append_diagnostic_log(
        logf,
        f"AUTO_COMMIT: staging pending changes ({subject_suffix})",
        out,
    )
    rc_add, _, e_add = git(wt_path, *git_add_all_args())
    if rc_add != 0:
        _append_diagnostic_log(logf, "AUTO_COMMIT: git add -A failed", e_add or "")
        return False

    code_staged, _, _ = git(wt_path, *git_diff_cached_quiet_args())
    if code_staged == 0:
        # Untracked-only edge cases should not happen after add -A with normal files; fail loudly.
        _append_diagnostic_log(
            logf,
            "AUTO_COMMIT: nothing staged after git add -A (unexpected)",
            out,
        )
        return False

    subj = truncate_subject(subject_suffix, prefix="chore(tasks): ", max_total=50)
    rc, _, e = git(
        wt_path,
        "-c",
        f"user.name={GIT_IDENTITY_NAME}",
        "-c",
        f"user.email={GIT_IDENTITY_EMAIL}",
        "commit",
        "-m",
        subj,
    )
    if rc != 0:
        _append_diagnostic_log(logf, "AUTO_COMMIT: git commit failed", e or "")
        return False
    return True


@dataclass
class AutoFocusConfig:
    primary: Path
    harness: Harness
    plan_model: str
    execute_model: str
    progress: ProgressMode = "off"
    implement_rounds_max: int = IMPLEMENT_ROUNDS_MAX
    improve_implement_max: int = IMPROVE_IMPLEMENT_MAX
    conflict_rounds_max: int = CONFLICT_ROUNDS_MAX
    allow_agent_pick: bool = False
    cleanup_on_exit: bool = False
    task_arg: str = ""
    stats: SessionStats = field(default_factory=SessionStats)
    progress_agent_step: int = 0
    cycles_done_entry: int = 0
    max_cycles_str: str = ""
    session_deadline_epoch: str = ""
    current_wt_path: Path | None = None
    runner_id: str = "default"
    held_workspace_claim_lock_path: Path | None = None
    task_id: str = ""
    rotate_policy: TokenRotationPolicy = field(
        default_factory=lambda: TokenRotationPolicy(
            rotate_threshold=ROTATE_THRESHOLD_TOKENS,
            warn_threshold=ROTATE_WARN_THRESHOLD_TOKENS,
        )
    )
    token_warning_emitted: bool = False
    no_progress_loops: int = 0
    last_failure_kind: FailureKind | None = None
    last_failure_detail: str = ""
    last_agent_error_detail: str = ""
    resume_handoff: str = ""
    resume_handoff_pending: bool = False
    trunk_branch_override: str | None = None
    max_phase_rounds: int = 20
    verification_required: bool = True
    merge_required: bool = True
    phase_agent_rounds: int = 0

    def _run_agent(
        self,
        wt: Path,
        model: str,
        prompt_body: str,
        logf: Path,
        label: str,
    ) -> int:
        use_json = self.progress != "off" and self.harness.capabilities.supports_stream_json
        tee = self.progress == "full" and self.harness.capabilities.supports_tee_output
        metrics: Path | None = None
        live_usage: dict[str, int] = {}
        live_usage_estimated = False
        self.last_agent_error_detail = ""
        if self.progress != "off" and use_json and self.harness.capabilities.supports_metrics_output:
            metrics = logf.parent / f".metrics-{secrets.token_hex(4)}.txt"

        def handle_run_event(event) -> None:
            nonlocal live_usage_estimated
            if event.kind != "usage" or not event.usage_delta:
                return
            for key, value in event.usage_delta.items():
                live_usage[key] = live_usage.get(key, 0) + int(value)
            live_usage_estimated = live_usage_estimated or event.estimated
            if self.progress != "off":
                phase_bar(
                    self.progress_agent_step,
                    max_agent_steps(
                        self.implement_rounds_max,
                        self.improve_implement_max,
                        self.conflict_rounds_max,
                    ),
                    label,
                    model=model,
                    token_total=self.stats.rotation_tokens() + _usage_rotation_tokens(live_usage),
                    token_estimated=live_usage_estimated,
                )

        request = self.harness.prepare(
            RunRequest(
                cwd=wt,
                model=model,
                prompt=prompt_body,
                log_file=logf,
                use_stream_json=use_json,
                tee_output=tee,
                metrics_out=metrics,
                watchdog=RunWatchdog(
                    stall_timeout_sec=STREAM_STALL_TIMEOUT_SEC if STREAM_STALL_TIMEOUT_SEC > 0 else None,
                    total_runtime_timeout_sec=(
                        TOTAL_RUNTIME_TIMEOUT_SEC if TOTAL_RUNTIME_TIMEOUT_SEC > 0 else None
                    ),
                ),
                event_callback=handle_run_event if self.progress != "off" else None,
            )
        )
        t0 = time.monotonic()
        if self.progress != "off":
            self.progress_agent_step += 1
            phase_bar(
                self.progress_agent_step,
                max_agent_steps(
                    self.implement_rounds_max,
                    self.improve_implement_max,
                    self.conflict_rounds_max,
                ),
                label,
                model=model,
                token_total=self.stats.rotation_tokens(),
            )
        try:
            result = self.harness.run(request)
            rc = result.exit_code
            usage = result.usage
        except OSError as exc:
            rc, usage = 1, {}
            self.last_agent_error_detail = f"{type(exc).__name__}: {exc}"
        committed_usage = usage or live_usage
        self.stats.add_tokens(committed_usage)
        update_resume_runtime_state(
            self.primary,
            runner_id=self.runner_id,
            total_tokens=self.stats.rotation_tokens(),
            token_warning_emitted=self.token_warning_emitted,
        )
        wall = time.monotonic() - t0
        self.stats.add_step_wall(wall)
        summary = f"wall_s={wall:.1f}"
        if self.last_agent_error_detail:
            summary = f"{self.last_agent_error_detail}; {summary}"
        if metrics and metrics.is_file() and metrics.stat().st_size > 0:
            summary = metrics.read_text(encoding="utf-8", errors="replace")[:800] + f"; wall_s={wall:.1f}"
            metrics.unlink(missing_ok=True)
        if self.progress != "off":
            step_done(
                label,
                summary,
                model=model,
                token_total=self.stats.rotation_tokens(),
                token_estimated=bool(not usage and committed_usage and live_usage_estimated),
            )
        return rc

    def _sub(self, name: str, rel_task: str, plan_rel: str) -> str:
        prompt_body = render_prompt(
            name,
            primary=self.primary,
            task_rel=rel_task,
            plan_rel=plan_rel,
            verify_commands=verify_commands_markdown(self.primary),
            task_id=self.task_id,
        )
        if self.resume_handoff_pending and self.resume_handoff.strip():
            self.resume_handoff_pending = False
            return f"{self.resume_handoff.rstrip()}\n\n---\n\n{prompt_body}"
        return prompt_body

    def token_state(self, logf: Path) -> str:
        total_tokens = self.stats.rotation_tokens()
        state = self.rotate_policy.classify(total_tokens)
        if state == "warn" and not self.token_warning_emitted:
            _append_diagnostic_log(
                logf,
                "TOKEN_WARN",
                (
                    f"token_total={total_tokens} "
                    f"warn_threshold={self.rotate_policy.warn_threshold} "
                    f"rotate_threshold={self.rotate_policy.rotate_threshold}"
                ),
            )
            self.token_warning_emitted = True
        return state


def _release_task_lock(cfg: AutoFocusConfig) -> None:
    if cfg.held_workspace_claim_lock_path is not None:
        release_lock(cfg.held_workspace_claim_lock_path)
        cfg.held_workspace_claim_lock_path = None


def _task_is_complete(primary: Path, task_id: str, task_path: Path) -> bool:
    st = read_task_job_status(primary, task_id) if task_id.strip() else None
    if st is not None and st.completed:
        return True
    if not task_path.is_file():
        return False
    return not task_has_pending(task_path)


def _try_workspace_claim_lock(cfg: AutoFocusConfig, primary: Path, task_abs: Path) -> bool:
    tid = task_id_from_resolved_path(task_abs)
    wlp = workspace_task_claim_lock_path(primary, tid)
    if not try_acquire_task_lock(wlp):
        return False
    cfg.held_workspace_claim_lock_path = wlp
    cfg.task_id = tid
    return True


def _sync_job_status_files(
    cfg: AutoFocusConfig,
    *,
    wt_path: Path,
    br_name: str,
    rel_task: str,
    phase: str,
) -> None:
    if not cfg.task_id.strip():
        return
    title = ""
    tp = wt_path / rel_task
    if tp.is_file():
        title = task_label(tp)
    prev = read_task_job_status(cfg.primary, cfg.task_id)
    write_task_job_status(
        cfg.primary,
        TaskJobStatus(
            task_id=cfg.task_id,
            rel_task=rel_task,
            stage="in-progress",
            owning_session_id=cfg.runner_id,
            worktree_path=str(wt_path),
            branch=br_name,
            task_title=title or (prev.task_title if prev else ""),
            display_name=(prev.display_name if prev else ""),
            ai_summary=(prev.ai_summary if prev else ""),
            display_name_source=(prev.display_name_source if prev else ""),
            naming_content_hash=(prev.naming_content_hash if prev else ""),
            artifacts=list(prev.artifacts) if prev and prev.artifacts else [],
            completed=bool(prev.completed) if prev else False,
            cleanup_pending=bool(prev.cleanup_pending) if prev else False,
            review_required=bool(prev.review_required) if prev else False,
        ),
    )
    write_session_job_status(
        cfg.primary,
        SessionJobStatus(
            session_id=cfg.runner_id,
            workspace_root=str(cfg.primary.resolve()),
            active_task_id=cfg.task_id,
            rel_task=rel_task,
            phase=phase,
            worktree_path=str(wt_path),
            branch=br_name,
        ),
    )


def _finalize_review_required(
    cfg: AutoFocusConfig,
    *,
    wt_path: Path,
    rel_task: str,
    logf: Path,
    br_name: str,
) -> int:
    primary = cfg.primary
    _append_phase_log(logf, "REVIEW_REQUIRED_MAX_PHASE_ROUNDS")
    new_rel = rel_task
    try:
        tasks_lock_remove(primary, (primary / new_rel).resolve())
    except OSError:
        pass
    title = ""
    tp = wt_path / new_rel
    if tp.is_file():
        title = task_label(tp)
    prev = read_task_job_status(primary, cfg.task_id)
    write_task_job_status(
        primary,
        TaskJobStatus(
            task_id=cfg.task_id,
            rel_task=new_rel,
            stage="review-required",
            owning_session_id="",
            worktree_path=str(wt_path),
            branch=br_name,
            task_title=title,
            display_name=(prev.display_name if prev else ""),
            ai_summary=(prev.ai_summary if prev else ""),
            display_name_source=(prev.display_name_source if prev else ""),
            naming_content_hash=(prev.naming_content_hash if prev else ""),
            artifacts=list(prev.artifacts) if prev and prev.artifacts else [],
            cleanup_pending=bool(prev.cleanup_pending) if prev else False,
            review_required=True,
        ),
    )
    write_session_job_status(
        primary,
        SessionJobStatus(
            session_id=cfg.runner_id,
            workspace_root=str(primary.resolve()),
            active_task_id="",
            rel_task=new_rel,
            phase="REVIEW_REQUIRED",
            worktree_path=str(wt_path),
            branch=br_name,
        ),
    )
    clear_resume(primary, runner_id=cfg.runner_id)
    _release_task_lock(cfg)
    cfg.current_wt_path = None
    try:
        bump_summary(primary, tasks_review_required=1)
    except OSError:
        pass
    emit_lifecycle_event(
        primary,
        event="task_review_required",
        outcome="max_phase_rounds",
        session_id=cfg.runner_id,
        task_id=cfg.task_id,
        harness=cfg.harness.id,
        plan_model=cfg.plan_model,
        execute_model=cfg.execute_model,
        duration_sec=max(0.0, time.time() - cfg.stats.started_wall),
        cycles=cfg.phase_agent_rounds,
        metadata={"max_phase_rounds": cfg.max_phase_rounds},
    )
    return 4


def _maybe_stop_for_phase_budget(
    cfg: AutoFocusConfig,
    *,
    phase: str,
    ctx: _PhaseBudgetCtx,
) -> int | None:
    if phase not in _COUNTED_AGENT_PHASES:
        return None
    limit = max(1, cfg.max_phase_rounds)
    if cfg.phase_agent_rounds < limit:
        return None
    tp = ctx.wt_path / ctx.rel_task
    if not tp.is_file() or _task_is_complete(cfg.primary, cfg.task_id, tp):
        return None
    return _finalize_review_required(
        cfg,
        wt_path=ctx.wt_path,
        rel_task=ctx.rel_task,
        logf=ctx.logf,
        br_name=ctx.br_name,
    )


def _log_tail(logf: Path, *, lines: int = 80) -> str:
    if not logf.is_file():
        return ""
    raw_lines = logf.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(raw_lines[-lines:])


def _worktree_fingerprint(wt_path: Path) -> str:
    code, out, _ = git(wt_path, "status", "--porcelain=v1")
    return out if code == 0 else ""


def _progress_snapshot(wt_path: Path, rel_task: str) -> ProgressSnapshot:
    pending, _done = count_checklist(wt_path / rel_task)
    code, head, _ = git(wt_path, "rev-parse", "HEAD")
    return ProgressSnapshot(
        pending_count=pending,
        head=head.strip() if code == 0 else "",
        worktree_fingerprint=_worktree_fingerprint(wt_path),
    )


def _run_phase_agent(
    cfg: AutoFocusConfig,
    *,
    phase: str,
    prompt_name: str,
    wt_path: Path,
    rel_task: str,
    plan_rel: str,
    logf: Path,
    label: str,
    phase_budget: _PhaseBudgetCtx | None = None,
) -> int:
    cfg.last_failure_kind = None
    cfg.last_failure_detail = ""
    if phase_budget is not None:
        early = _maybe_stop_for_phase_budget(cfg, phase=phase, ctx=phase_budget)
        if early is not None:
            return early
    before = _progress_snapshot(wt_path, rel_task)
    model = phase_model_for(phase, plan_model=cfg.plan_model, execute_model=cfg.execute_model)
    rc = cfg._run_agent(wt_path, model, cfg._sub(prompt_name, rel_task, plan_rel), logf, label)
    after = _progress_snapshot(wt_path, rel_task)
    if rc != 0:
        classification = cfg.harness.classify_failure(
            FailureContext(
                summary=f"{label} failed",
                detail=_failure_detail(logf, cfg.last_agent_error_detail),
                no_progress_streak=cfg.no_progress_loops,
                before=before,
                after=after,
            )
        )
        cfg.last_failure_kind = classification.kind
        cfg.last_failure_detail = classification.detail
        _append_diagnostic_log(
            logf,
            f"{label}: classified failure",
            f"{classification.kind.value}\n{classification.detail}",
        )
        return 1

    made_progress = (
        before.pending_count != after.pending_count
        or before.head != after.head
        or before.worktree_fingerprint != after.worktree_fingerprint
    )
    if phase in ("IMPLEMENT", "IMPROVE_EXECUTE"):
        if made_progress:
            cfg.no_progress_loops = 0
        else:
            cfg.no_progress_loops += 1
        if not made_progress and cfg.no_progress_loops >= NO_PROGRESS_LOOPS_MAX:
            classification = cfg.harness.classify_failure(
                FailureContext(
                    summary=f"{label} made no progress",
                    detail="Task checklist and git state did not change.",
                    no_progress_streak=cfg.no_progress_loops,
                    before=before,
                    after=after,
                )
            )
            cfg.last_failure_kind = classification.kind
            cfg.last_failure_detail = classification.detail
            _append_diagnostic_log(
                logf,
                f"{label}: gutter detection",
                f"{classification.kind.value}\n{classification.detail}",
            )
            return 1

    if phase in _COUNTED_AGENT_PHASES:
        cfg.phase_agent_rounds += 1
    token_state = cfg.token_state(logf)
    if token_state == "rotate":
        _append_diagnostic_log(
            logf,
            "TOKEN_ROTATE",
            (
                f"token_total={cfg.stats.rotation_tokens()} "
                f"rotate_threshold={cfg.rotate_policy.rotate_threshold}"
            ),
        )
        return 3
    return 0


def _run_non_task_phase_agent(
    cfg: AutoFocusConfig,
    *,
    cwd: Path,
    model: str,
    prompt_body: str,
    logf: Path,
    label: str,
) -> int:
    cfg.last_failure_kind = None
    cfg.last_failure_detail = ""
    rc = cfg._run_agent(cwd, model, prompt_body, logf, label)
    if rc != 0:
        classification = cfg.harness.classify_failure(
            FailureContext(
                summary=f"{label} failed",
                detail=_failure_detail(logf, cfg.last_agent_error_detail),
                no_progress_streak=cfg.no_progress_loops,
            )
        )
        cfg.last_failure_kind = classification.kind
        cfg.last_failure_detail = classification.detail
        _append_diagnostic_log(
            logf,
            f"{label}: classified failure",
            f"{classification.kind.value}\n{classification.detail}",
        )
        return 1
    token_state = cfg.token_state(logf)
    if token_state == "rotate":
        _append_diagnostic_log(
            logf,
            "TOKEN_ROTATE",
            (
                f"token_total={cfg.stats.rotation_tokens()} "
                f"rotate_threshold={cfg.rotate_policy.rotate_threshold}"
            ),
        )
        return 3
    return 0


def _teardown_plan_only_worktree(cfg: AutoFocusConfig, wt_path: Path, br_name: str, primary: Path) -> None:
    _release_task_lock(cfg)
    if wt_path.is_dir():
        git(primary, "worktree", "remove", "-f", str(wt_path))
    git(primary, "branch", "-D", br_name)
    cfg.current_wt_path = None


def _branch_checked_out_at(wt_path: Path) -> str:
    code, out, _ = git(wt_path, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        return ""
    name = (out or "").strip()
    if not name or name == "HEAD":
        return ""
    return name


def abandon_auto_pick_cycle_on_failure(
    cfg: AutoFocusConfig,
    *,
    resume_hint: ResumeState | None = None,
) -> None:
    """Tear down a failed cycle so ``sponte agent --auto`` can pick another task.

    Best-effort: clears resume, removes the worktree and task branch, releases the
    workspace claim lock, restores job rows, and clears the session active task.
    """
    primary = cfg.primary
    st = resume_hint if resume_hint is not None else load_resume(primary, runner_id=cfg.runner_id)

    wt_path: Path | None = cfg.current_wt_path
    if wt_path is None and st is not None and (st.wt_path or "").strip():
        wt_path = Path(st.wt_path)

    br_name = (st.branch if st else "").strip()
    if not br_name and wt_path is not None and wt_path.is_dir():
        br_name = _branch_checked_out_at(wt_path)

    tid = ((cfg.task_id or "").strip() or ((st.task_id if st else "") or "").strip())
    rel_for_backlog = (st.rel_task or "").strip() if st is not None else ""
    if not rel_for_backlog and tid:
        tjs0 = read_task_job_status(primary, tid)
        if tjs0 is not None:
            rel_for_backlog = (tjs0.rel_task or "").strip()

    clear_resume(primary, runner_id=cfg.runner_id)

    if rel_for_backlog:
        try:
            tasks_lock_remove(primary, (primary / rel_for_backlog).resolve())
        except OSError:
            pass

    if wt_path is not None and wt_path.is_dir() and worktree_registered(primary, wt_path):
        git(primary, "worktree", "remove", "-f", str(wt_path))

    if br_name.strip():
        git(primary, "branch", "-D", br_name)

    _release_task_lock(cfg)
    cfg.current_wt_path = None

    new_rel_for_session = ""
    if tid:
        tjs = read_task_job_status(primary, tid)
        title = (tjs.task_title if tjs else "") or ""
        rel_src = rel_for_backlog or ((tjs.rel_task if tjs else "") or "").strip()
        if rel_src:
            new_rel_for_session = _restore_task_to_backlog(primary, rel_src)
            write_task_job_status(
                primary,
                TaskJobStatus(
                    task_id=tid,
                    rel_task=new_rel_for_session,
                    stage="backlog",
                    owning_session_id="",
                    worktree_path="",
                    branch="",
                    task_title=title,
                ),
            )

    _clear_session_active_task(
        primary,
        cfg.runner_id,
        rel_task=new_rel_for_session,
        phase="",
        worktree_path="",
        branch="",
    )


def run_one_cycle(
    cfg: AutoFocusConfig,
    *,
    use_resume: bool,
    resume_state: ResumeState | None = None,
    stop_after_plan: bool = False,
) -> int:
    """
    Returns 0 success, 1 error, 2 no actionable task, 3 rotate session, 4 unused (internal).
    Mutates cfg.task_arg consumed after successful cycle by caller.
    """
    primary = cfg.primary
    rel_task = ""
    plan_rel = ""
    wt_path = Path()
    br_name = ""
    main_ref = ""
    logf = Path()
    phase = "PLAN"
    implement_next = 1
    improve_i = 1
    improve_j = 0
    conflict_next = 1

    cfg.progress_agent_step = 0
    cfg.last_failure_kind = None
    cfg.last_failure_detail = ""

    if use_resume:
        st = resume_state or load_resume(
            primary,
            runner_id=cfg.runner_id,
        )
        if st is None:
            return _fatal_resume_error(
                cfg,
                f"No resume state found for runner '{cfg.runner_id}'. Clear resume or start a new session.",
            )
        if not st.wt_path.strip():
            return _fatal_resume_error(
                cfg,
                "Resume state is invalid: missing worktree path. Clear resume or start a new session.",
            )
        wt_resume_path = Path(st.wt_path)
        if not worktree_registered(primary, wt_resume_path):
            return _fatal_resume_error(
                cfg,
                f"Resume worktree is not registered: {wt_resume_path}. Clear resume or start a new session.",
            )
        if not wt_resume_path.is_dir():
            return _fatal_resume_error(
                cfg,
                f"Resume state points to a missing worktree directory: {wt_resume_path}. "
                "Clear resume or start a new session.",
            )
        logf = Path(st.logf)
        wt_path = wt_resume_path
        br_name = st.branch
        main_ref = st.main_ref
        rel_task = st.rel_task
        plan_rel = st.plan_rel
        phase = st.phase
        implement_next = st.implement_next
        improve_i = st.improve_i
        improve_j = st.improve_j
        conflict_next = st.conflict_next
        cfg.plan_model = st.plan_model or cfg.plan_model
        cfg.execute_model = st.agent_model or cfg.execute_model
        if st.agent_kind:
            cfg.harness = resolve_harness(primary, st.agent_kind)
        cfg.allow_agent_pick = st.allow_agent_pick.lower() == "true"
        cfg.task_arg = st.task_arg
        cfg.cycles_done_entry = st.cycles_done
        cfg.max_cycles_str = st.max_cycles
        cfg.session_deadline_epoch = st.session_deadline_epoch or cfg.session_deadline_epoch
        cfg.current_wt_path = wt_path
        # Rotation is scoped to the current resumed process, not cumulative history.
        cfg.stats.total_token_count = st.total_tokens
        cfg.stats.rotation_token_count = st.total_tokens
        cfg.no_progress_loops = st.no_progress_loops
        cfg.token_warning_emitted = st.token_warning_emitted.lower() == "true"
        handoff_path = rotation_handoff_file(primary, runner_id=cfg.runner_id)
        cfg.resume_handoff = handoff_path.read_text(encoding="utf-8", errors="replace") if handoff_path.is_file() else ""
        handoff_path.unlink(missing_ok=True)
        cfg.resume_handoff_pending = bool(cfg.resume_handoff.strip())
        cfg.task_id = (st.task_id or "").strip()
        if not cfg.task_id:
            tpath = wt_path / rel_task
            if tpath.is_file():
                cfg.task_id = task_id_from_resolved_path((primary / concrete_task_rel(primary, rel_task)).resolve())
        touch_session_job_folder(primary, cfg.runner_id)
        oc, dc = count_checklist(wt_path / rel_task)
        label = task_label(wt_path / rel_task)
        if cfg.progress != "off":
            banner(f"Resume cycle — {rel_task}")
            task_block(rel_task, label, oc, dc)
            step_done("resume", f"phase={phase}")
    else:
        auto_focus_logs_dir(
            primary,
            runner_id=cfg.runner_id,
        ).mkdir(parents=True, exist_ok=True)
        touch_session_job_folder(primary, cfg.runner_id)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        logf = (
            auto_focus_logs_dir(
                primary,
                runner_id=cfg.runner_id,
            )
            / f"run-{ts}.log"
        )
        logf.write_text("", encoding="utf-8")

        code, task_abs = _select_next_task_abs(cfg)
        if code == 2:
            return 2
        if code != 0 or task_abs is None:
            return 1
        task_rel = task_abs.relative_to(primary).as_posix()

        safe_tid = sanitize_job_segment(cfg.task_id)
        wt_path = worktrees_base(primary) / f"wt-{safe_tid}"
        br_name = f"ralph/wt-{safe_tid}"[:200]
        main_ref = resolve_trunk_branch_ref(primary, cli_override=cfg.trunk_branch_override)

        oc, dc = count_checklist(task_abs)
        label = task_label(task_abs)
        if cfg.progress != "off":
            banner(f"New cycle — {task_rel}")
            task_block(task_rel, label, oc, dc)

        _append_phase_log(logf, "GIT_WORKTREE_ADD")
        rc, _, err = git(primary, "worktree", "add", "-b", br_name, str(wt_path), main_ref)
        if rc != 0:
            logf.write_text(logf.read_text(encoding="utf-8") + err, encoding="utf-8")
            _release_task_lock(cfg)
            return 1
        cfg.current_wt_path = wt_path
        cfg.resume_handoff = ""
        cfg.resume_handoff_pending = False

        _record_base(primary, wt_path, task_rel)
        init_task_job_artifacts(
            primary,
            task_id=cfg.task_id,
            task_abs=task_abs,
            session_id=cfg.runner_id,
            rel_task=task_rel,
        )
        claimed = _claim_task_on_primary(cfg, task_abs, task_rel, logf)
        if claimed is None:
            _release_task_lock(cfg)
            return 1
        rel_task = claimed
        _maybe_refresh_task_display_name(cfg, wt_path, rel_task, logf)
        _print_picked_task_table(cfg, task_abs)
        plan_path = plan_file_for_task(primary, Path(rel_task).stem)
        plan_rel = plan_path.resolve().as_posix()
        plans_dir(primary).mkdir(parents=True, exist_ok=True)

        phase = "PLAN"
        implement_next = 1
        improve_i = 1
        improve_j = 0
        conflict_next = 1
        cfg.no_progress_loops = 0
        cfg.token_warning_emitted = False
        _persist(
            cfg,
            logf,
            wt_path,
            br_name,
            main_ref,
            rel_task,
            plan_rel,
            phase,
            implement_next,
            improve_i,
            improve_j,
            conflict_next,
        )
        emit_lifecycle_event(
            primary,
            event="task_claimed",
            outcome="ok",
            session_id=cfg.runner_id,
            task_id=cfg.task_id,
            harness=cfg.harness.id,
            plan_model=cfg.plan_model,
            execute_model=cfg.execute_model,
            metadata={
                "rel_task": rel_task,
                "branch": br_name,
                "worktree_path": str(wt_path),
            },
        )

    cfg.phase_agent_rounds = 0

    def _pb() -> _PhaseBudgetCtx:
        return _PhaseBudgetCtx(
            wt_path,
            rel_task,
            logf,
            br_name,
            main_ref,
            plan_rel,
            implement_next,
            improve_i,
            improve_j,
            conflict_next,
        )

    # PLAN
    if phase == "PLAN":
        _append_phase_log(logf, "PLAN")
        rc = _run_phase_agent(
            cfg,
            phase="PLAN",
            prompt_name="plan",
            wt_path=wt_path,
            rel_task=rel_task,
            plan_rel=plan_rel,
            logf=logf,
            label="PLAN",
            phase_budget=_pb(),
        )
        if rc == 4:
            return 0
        if rc == 1:
            if stop_after_plan:
                _release_task_lock(cfg)
            return rc
        if stop_after_plan:
            if rc == 3:
                _teardown_plan_only_worktree(cfg, wt_path, br_name, primary)
                return 3
            if rc == 0:
                _register_plan_file_artifact(cfg, plan_rel)
            _teardown_plan_only_worktree(cfg, wt_path, br_name, primary)
            return 0
        if rc == 0:
            _register_plan_file_artifact(cfg, plan_rel)
        phase = "IMPLEMENT"
        implement_next = 1
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
        if rc == 3:
            return 3

    # IMPLEMENT
    if phase == "IMPLEMENT":
        n = implement_next - 1
        while n < cfg.implement_rounds_max and (n == 0 or not _task_is_complete(cfg.primary, cfg.task_id, wt_path / rel_task)):
            n += 1
            implement_next = n
            _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
            _append_phase_log(logf, f"IMPLEMENT_{n}")
            rc = _run_phase_agent(
                cfg,
                phase="IMPLEMENT",
                prompt_name="implement",
                wt_path=wt_path,
                rel_task=rel_task,
                plan_rel=plan_rel,
                logf=logf,
                label=f"IMPLEMENT_{n}",
                phase_budget=_pb(),
            )
            if rc == 4:
                return 0
            if rc == 1:
                return rc
            implement_next = n + 1
            _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
            if rc == 3:
                return 3
        if not _task_is_complete(cfg.primary, cfg.task_id, wt_path / rel_task):
            return 1
        phase = "IMPROVE_REVIEW"
        improve_i = 1
        improve_j = 0
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)

    # IMPROVE
    if phase in ("IMPROVE", "IMPROVE_REVIEW"):
        i, j = improve_i, improve_j
        while i <= 3:
            if j == 0:
                _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, i, 0, conflict_next)
                _append_phase_log(logf, f"IMPROVE_{i}")
                rc = _run_phase_agent(
                    cfg,
                    phase="IMPROVE_REVIEW",
                    prompt_name="improve",
                    wt_path=wt_path,
                    rel_task=rel_task,
                    plan_rel=plan_rel,
                    logf=logf,
                    label=f"IMPROVE_{i}",
                    phase_budget=_pb(),
                )
                if rc == 4:
                    return 0
                if rc == 1:
                    return rc
                j = 1
                _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, i, j, conflict_next)
                if rc == 3:
                    return 3
            while j <= cfg.improve_implement_max:
                _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, i, j, conflict_next)
                _append_phase_log(logf, f"IMPROVE_{i}_IMPLEMENT_{j}")
                rc = _run_phase_agent(
                    cfg,
                    phase="IMPROVE_EXECUTE",
                    prompt_name="implement",
                    wt_path=wt_path,
                    rel_task=rel_task,
                    plan_rel=plan_rel,
                    logf=logf,
                    label=f"IMPROVE_{i}_IMPLEMENT_{j}",
                    phase_budget=_pb(),
                )
                if rc == 4:
                    return 0
                if rc == 1:
                    return rc
                j += 1
                _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, i, j, conflict_next)
                if rc == 3:
                    return 3
            i += 1
            j = 0
            _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, i, j, conflict_next)
        improve_i = i
        improve_j = j
        phase = "WRAP"
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)

    if phase == "WRAP":
        _append_phase_log(logf, "WRAP_COMMIT")
        rc = _run_phase_agent(
            cfg,
            phase="WRAP",
            prompt_name="wrap_commit",
            wt_path=wt_path,
            rel_task=rel_task,
            plan_rel=plan_rel,
            logf=logf,
            label="WRAP_COMMIT",
            phase_budget=_pb(),
        )
        if rc == 4:
            return 0
        if rc == 1:
            return rc
        _auto_finalize_task_branch(primary, wt_path, rel_task)
        if cfg.verification_required:
            phase = "VERIFY"
        else:
            _append_phase_log(logf, "VERIFY_SKIPPED_POLICY")
            phase = "MERGE"
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
        if rc == 3:
            return 3

    if phase == "VERIFY":
        _append_phase_log(logf, "VERIFY")
        rc = _run_phase_agent(
            cfg,
            phase="VERIFY",
            prompt_name="verify",
            wt_path=wt_path,
            rel_task=rel_task,
            plan_rel=plan_rel,
            logf=logf,
            label="VERIFY",
            phase_budget=_pb(),
        )
        if rc == 4:
            return 0
        if rc == 1:
            return rc
        if not _commit_worktree_pending_if_dirty(wt_path, logf, "verify before merge"):
            return 1
        phase = "MERGE"
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
        if rc == 3:
            return 3

    if phase in ("MERGE", "MERGE_CONFLICT", "PRIMARY_PREMERGE"):
        try:
            with (
                merge_phase_locked(primary, main_ref),
                repo_merge_lock_held(
                    primary,
                    cfg.runner_id,
                    load_workspace_settings(primary).resolved_merge_backoff(),
                    float(MERGE_LOCK_TIMEOUT_SEC),
                ),
            ):
                # Resume at MERGE skips VERIFY and any dirty worktree would block merge.
                # Commit pending changes here too.
                merge_dirty_before = not worktree_clean(wt_path)
                if merge_dirty_before:
                    _append_phase_log(logf, "PRE_MERGE_COMMIT")
                    if not _commit_worktree_pending_if_dirty(wt_path, logf, "pre-merge agent"):
                        merge_precheck_failed(
                            "Could not commit pending worktree changes before merge.",
                            "See run log (AUTO_COMMIT sections). Fix git state in the worktree, then retry with `sponte session-resume SESSION_ID`.",
                        )
                        return 1
                    if cfg.progress != "off":
                        step_done(
                            "pre-merge",
                            "worktree had uncommitted changes; committed before merge",
                        )
                if not worktree_clean(wt_path):
                    _code, wt_porcelain, _ = git(wt_path, "status", "--porcelain")
                    wt_detail = wt_porcelain or "(git status --porcelain empty but tree not clean — unexpected)"
                    _append_diagnostic_log(
                        logf,
                        "MERGE blocked: worktree is not clean",
                        wt_detail,
                    )
                    merge_precheck_failed(
                        "Worktree still has uncommitted changes after pre-merge commit; commit or discard them, then retry.",
                        wt_detail,
                    )
                    return 1

                if cfg.merge_required:
                    start_pre_round = conflict_next if phase == "PRIMARY_PREMERGE" else 1
                    pre_state = primary_merge_precheck_state(primary)

                    if phase == "PRIMARY_PREMERGE" and pre_state.kind == PrimaryPrecheckKind.CLEAN:
                        phase = "MERGE"
                        conflict_next = 1
                        _persist(
                            cfg,
                            logf,
                            wt_path,
                            br_name,
                            main_ref,
                            rel_task,
                            plan_rel,
                            phase,
                            implement_next,
                            improve_i,
                            improve_j,
                            conflict_next,
                        )
                    elif pre_state.kind != PrimaryPrecheckKind.CLEAN:
                        _append_diagnostic_log(
                            logf,
                            "Merge precheck: primary not clean (outside Sponte-ignored paths)",
                            pre_state.detail or pre_state.kind.value,
                        )
                        merge_precheck_warning(
                            "Primary checkout is not clean before Ralph merge; see run log for paths.",
                            pre_state.detail,
                        )
                        if pre_state.kind == PrimaryPrecheckKind.REBASE_IN_PROGRESS:
                            merge_precheck_failed(
                                "Primary checkout has a rebase in progress.",
                                pre_state.detail,
                            )
                            return 1
                        if pre_state.kind == PrimaryPrecheckKind.CONFLICT_DIRTY:
                            precheck_rc = _resolve_primary_precheck_conflicts(
                                cfg,
                                logf,
                                wt_path,
                                br_name,
                                main_ref,
                                rel_task,
                                plan_rel,
                                implement_next,
                                improve_i,
                                improve_j,
                                start_pre_round,
                            )
                            if precheck_rc == 3:
                                return 3
                            if precheck_rc != 0:
                                merge_precheck_failed(
                                    "Could not resolve primary merge conflicts before Ralph merge.",
                                    "See run log (PRIMARY_PREMERGE sections). Fix git state on the primary checkout, then retry with `sponte session-resume SESSION_ID`.",
                                )
                                return 1
                            phase = "MERGE"
                            conflict_next = 1
                            _persist(
                                cfg,
                                logf,
                                wt_path,
                                br_name,
                                main_ref,
                                rel_task,
                                plan_rel,
                                phase,
                                implement_next,
                                improve_i,
                                improve_j,
                                conflict_next,
                            )
                            if cfg.progress != "off":
                                step_done(
                                    "primary pre-merge",
                                    "resolved conflicts on primary checkout",
                                    model=cfg.execute_model,
                                    token_total=cfg.stats.rotation_tokens(),
                                )
                        else:
                            merge_precheck_failed(
                                "Primary has local changes outside Sponte-ignored paths; commit or discard them, then retry.",
                                pre_state.detail,
                            )
                            return 1

                    pre_final = primary_merge_precheck_state(primary)
                    if pre_final.kind != PrimaryPrecheckKind.CLEAN:
                        merge_precheck_failed(
                            "Primary checkout is still not ready to merge after precheck.",
                            pre_final.detail or pre_final.kind.value,
                        )
                        return 1

                    mh_code, _, _ = git(primary, *git_verify_ref_args("MERGE_HEAD"))
                    if mh_code == 0 and phase != "MERGE_CONFLICT":
                        merge_head_hint = (
                            "Resolve or abort the in-progress merge on the primary checkout (e.g. git merge --abort), "
                            "then retry with `sponte session-resume SESSION_ID`."
                        )
                        _append_diagnostic_log(
                            logf,
                            "MERGE blocked: MERGE_HEAD exists on primary but phase is not MERGE_CONFLICT",
                            merge_head_hint,
                        )
                        merge_precheck_failed(
                            "Primary checkout has an unfinished merge (MERGE_HEAD).",
                            merge_head_hint,
                        )
                        return 1

                    if phase == "MERGE_CONFLICT" and mh_code != 0:
                        phase = "MERGE"
                        conflict_next = 1
                        _persist(
                            cfg,
                            logf,
                            wt_path,
                            br_name,
                            main_ref,
                            rel_task,
                            plan_rel,
                            phase,
                            implement_next,
                            improve_i,
                            improve_j,
                            conflict_next,
                        )
                else:
                    _append_phase_log(logf, "PRIMARY_MERGE_PRECHECK_SKIPPED_POLICY")
                    if phase in ("PRIMARY_PREMERGE", "MERGE_CONFLICT"):
                        phase = "MERGE"
                        conflict_next = 1
                        _persist(
                            cfg,
                            logf,
                            wt_path,
                            br_name,
                            main_ref,
                            rel_task,
                            plan_rel,
                            phase,
                            implement_next,
                            improve_i,
                            improve_j,
                            conflict_next,
                        )

                _append_phase_log(logf, f"MERGE_TO_{main_ref}")
                feature_already_merged = is_branch_merged_into(primary, br_name, main_ref)
                if not cfg.merge_required:
                    _append_phase_log(logf, "MERGE_SKIPPED_POLICY")
                    if cfg.progress != "off":
                        msg = (
                            f"feature branch already merged into {main_ref}"
                            if feature_already_merged
                            else (
                                f"merge into {main_ref} skipped (policy.merge_required=false); "
                                "feature branch left unmerged on disk until you merge manually"
                            )
                        )
                        step_done(
                            "merge",
                            msg,
                            token_total=cfg.stats.rotation_tokens(),
                        )
                elif feature_already_merged:
                    if cfg.progress != "off":
                        step_done(
                            "merge",
                            f"feature branch already merged into {main_ref}",
                            token_total=cfg.stats.rotation_tokens(),
                        )
                elif phase == "MERGE_CONFLICT":
                    merge_rc = _resolve_merge_with_agent(
                        cfg,
                        logf,
                        br_name,
                        main_ref,
                        conflict_next,
                        wt_path,
                        rel_task,
                        plan_rel,
                        implement_next,
                        improve_i,
                        improve_j,
                    )
                    if merge_rc == 3:
                        return 3
                    if merge_rc != 0:
                        return 1
                elif _merge_feature_to_main(primary, br_name, main_ref, logf):
                    pass
                else:
                    merge_rc = _resolve_merge_with_agent(
                        cfg,
                        logf,
                        br_name,
                        main_ref,
                        1,
                        wt_path,
                        rel_task,
                        plan_rel,
                        implement_next,
                        improve_i,
                        improve_j,
                    )
                    if merge_rc == 3:
                        return 3
                    if merge_rc != 0:
                        return 1

                _archive_recorded_artifacts(cfg, wt_path)
                rc_rm, _, _ = git(primary, "worktree", "remove", str(wt_path))
                if rc_rm != 0 or wt_path.exists():
                    git(primary, "worktree", "remove", "-f", str(wt_path))
                rc_branch, _, br_err = git(primary, "branch", "-d", br_name)
                if rc_branch != 0:
                    if not cfg.merge_required:
                        git(primary, "branch", "-D", br_name)
                    else:
                        _append_diagnostic_log(
                            logf,
                            "git branch -d failed after merge",
                            br_err or "",
                        )
                        return 1
                clear_resume(
                    primary,
                    runner_id=cfg.runner_id,
                )
                _move_completed_on_primary(cfg, rel_task)
                _release_task_lock(cfg)
                cfg.stats.cycles_completed += 1
                cfg.current_wt_path = None
                try:
                    bump_summary(primary, tasks_completed=1)
                except OSError:
                    pass
                emit_lifecycle_event(
                    primary,
                    event="task_completed",
                    outcome="ok",
                    session_id=cfg.runner_id,
                    task_id=cfg.task_id,
                    harness=cfg.harness.id,
                    plan_model=cfg.plan_model,
                    execute_model=cfg.execute_model,
                    duration_sec=max(0.0, time.time() - cfg.stats.started_wall),
                    cycles=cfg.stats.agent_steps,
                    metadata={
                        "merge_into_trunk": cfg.merge_required,
                        "cycles_completed": cfg.stats.cycles_completed,
                    },
                )
                return 0
        except RepoMergeLockTimeoutError as e:
            _append_diagnostic_log(
                logf,
                "MERGE: timed out waiting for .sponte/locks/merge.lock",
                str(e),
            )
            merge_precheck_failed(
                "Another session holds the workspace merge lock for too long.",
                "Wait and retry, or remove a stale `.sponte/locks/merge.lock` if safe.",
            )
            return 1
        except LockWaitTimeoutError as e:
            _append_diagnostic_log(
                logf,
                f"MERGE: timed out waiting for merge-into-{main_ref} lock on primary",
                str(e),
            )
            merge_precheck_failed(
                f"Another Ralph runner is merging into local `{main_ref}` (or holding that merge lock) for too long.",
                "Wait and retry with `sponte session-resume SESSION_ID`, or adjust RALPH_MERGE_LOCK_TIMEOUT_SEC.",
            )
            return 1

    return 1


def _persist(
    cfg: AutoFocusConfig,
    logf: Path,
    wt_path: Path,
    br_name: str,
    main_ref: str,
    rel_task: str,
    plan_rel: str,
    phase: str,
    implement_next: int,
    improve_i: int,
    improve_j: int,
    conflict_next: int,
) -> None:
    st = ResumeState(
        schema_version=RESUME_SCHEMA_VERSION,
        primary=str(cfg.primary.resolve()),
        phase=phase,
        logf=str(logf),
        wt_path=str(wt_path),
        branch=br_name,
        main_ref=main_ref,
        rel_task=rel_task,
        plan_rel=plan_rel,
        implement_next=implement_next,
        improve_i=improve_i,
        improve_j=improve_j,
        conflict_next=conflict_next,
        cycles_done=cfg.cycles_done_entry,
        max_cycles=cfg.max_cycles_str,
        task_arg=cfg.task_arg,
        agent_kind=cfg.harness.id,
        plan_model=cfg.plan_model,
        agent_model=cfg.execute_model,
        allow_agent_pick="true" if cfg.allow_agent_pick else "false",
        session_deadline_epoch=cfg.session_deadline_epoch,
        total_tokens=cfg.stats.rotation_tokens(),
        no_progress_loops=cfg.no_progress_loops,
        token_warning_emitted="true" if cfg.token_warning_emitted else "false",
        resume_runner_id=cfg.runner_id,
        task_id=cfg.task_id,
    )
    write_resume(
        cfg.primary,
        st,
        runner_id=cfg.runner_id,
    )
    _sync_job_status_files(cfg, wt_path=wt_path, br_name=br_name, rel_task=rel_task, phase=phase)


def _select_next_task_abs(cfg: AutoFocusConfig) -> tuple[int, Path | None]:
    primary = cfg.primary
    try:
        tasks_lock_prune_missing(primary)
    except OSError:
        pass

    def _take_task_and_claim_lock(task_abs: Path) -> bool:
        if not _try_workspace_claim_lock(cfg, primary, task_abs):
            return False
        return True

    if cfg.task_arg:
        p = normalize_task_path(primary, cfg.task_arg)
        if not p.is_file():
            return (1, None)
        if path_is_tasks_locked(primary, p):
            return (2, None)
        if not _take_task_and_claim_lock(p):
            return (2, None)
        return (0, p)

    if not cfg.allow_agent_pick:
        return (2, None)

    ap_lp = agent_pick_lock_path(primary)
    try:
        acquire_lock_blocking(ap_lp, timeout_sec=AGENT_PICK_LOCK_TIMEOUT_SEC)
    except LockWaitTimeoutError:
        return (1, None)
    try:
        picked = _agent_pick_backlog_task(cfg)
        if picked is None:
            return (1, None)
        if not _take_task_and_claim_lock(picked):
            return (2, None)
        return (0, picked)
    finally:
        release_lock(ap_lp)


def _agent_pick_backlog_task(cfg: AutoFocusConfig) -> Path | None:
    primary = cfg.primary
    nf = next_task_file(primary)
    nf.parent.mkdir(parents=True, exist_ok=True)
    nf.unlink(missing_ok=True)
    logf = (
        auto_focus_logs_dir(
            primary,
            runner_id=cfg.runner_id,
        )
        / "agent-pick.log"
    )
    body = render_prompt(
        "agent_pick_task",
        primary=primary,
        task_rel="",
        plan_rel="",
        verify_commands="",
        claimed_tasks_snapshot=format_claimed_tasks_snapshot(primary),
        backlog_candidates=format_pending_backlog_for_prompt(primary),
    )
    _append_phase_log(logf, "AGENT_PICK_TASK")
    if cfg._run_agent(primary, cfg.plan_model, body, logf, "AGENT_PICK_TASK") != 0:
        _maybe_print_auto_pick_failure_help(
            cfg,
            "Plan-model pick failed (non-zero exit); see agent-pick.log in session logs.",
        )
        return None
    if not nf.is_file():
        _maybe_print_auto_pick_failure_help(
            cfg,
            "Plan model did not write the next-task path file.",
        )
        return None
    line = nf.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
    line = concrete_task_rel(primary, line)
    abs_p = normalize_task_path(primary, line)
    if not abs_p.is_file():
        _maybe_print_auto_pick_failure_help(
            cfg,
            "Next-task path is missing or does not resolve to a task markdown file.",
        )
        return None
    if path_is_tasks_locked(primary, abs_p):
        _maybe_print_auto_pick_failure_help(
            cfg,
            "Chosen task is path-locked (another session may hold it).",
        )
        return None
    return abs_p


def _maybe_print_auto_pick_failure_help(cfg: AutoFocusConfig, message: str) -> None:
    if cfg.progress == "off":
        return
    from rich.console import Console

    Console(stderr=True).print(f"[yellow]{message}[/yellow]")
    _print_selectable_tasks_table(cfg)


def _print_selectable_tasks_table(cfg: AutoFocusConfig) -> None:
    from rich.console import Console
    from rich.table import Table

    t = Table(title="Selectable tasks (markdown, not path-locked)")
    t.add_column("rel_path")
    t.add_column("task_id")
    t.add_column("display_name")
    for p in sorted(pending_selectable_task_paths(cfg.primary)):
        tid = task_id_from_resolved_path(p)
        st = read_task_job_status(cfg.primary, tid)
        t.add_row(
            p.relative_to(cfg.primary).as_posix(),
            tid,
            (st.display_name if st and st.display_name else task_label(p)),
        )
    Console().print(t)


def _print_picked_task_table(cfg: AutoFocusConfig, task_abs: Path) -> None:
    from rich.console import Console
    from rich.table import Table

    if cfg.progress == "off":
        return
    st = read_task_job_status(cfg.primary, cfg.task_id)
    display_name = task_label(task_abs)
    if st is not None and (st.display_name or "").strip():
        display_name = st.display_name
    t = Table(title="Picked task")
    t.add_column("task_id")
    t.add_column("rel_path")
    t.add_column("lock_path")
    t.add_column("session")
    t.add_column("display_name")
    t.add_row(
        cfg.task_id,
        task_abs.relative_to(cfg.primary).as_posix(),
        task_abs.resolve().as_posix(),
        cfg.runner_id,
        display_name,
    )
    Console().print(t)


def _maybe_refresh_task_display_name(
    cfg: AutoFocusConfig,
    wt_path: Path,
    rel_task: str,
    logf: Path,
) -> None:
    tpath = wt_path / rel_task
    if not tpath.is_file():
        return
    text = tpath.read_text(encoding="utf-8", errors="replace")
    nh = naming_content_hash(text)
    prev = read_task_job_status(cfg.primary, cfg.task_id)
    if prev is not None and prev.naming_content_hash == nh and (prev.display_name or "").strip():
        return
    out = naming_reply_file(cfg.primary, cfg.task_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    excerpt = text[:6000]
    body = render_prompt(
        "task_display_name",
        primary=cfg.primary,
        task_rel=rel_task,
        plan_rel="",
        task_body_excerpt=excerpt,
        naming_reply_path=str(out),
    )
    rc = cfg._run_agent(wt_path, cfg.plan_model, body, logf, "TASK_DISPLAY_NAME")
    label = task_label(tpath)
    display_name = (label or Path(rel_task).stem)[:60]
    ai_summary = ""
    source = "fallback"
    if rc == 0 and out.is_file():
        try:
            raw = json.loads(out.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict):
                dn = str(raw.get("display_name", "")).strip()
                sm = str(raw.get("ai_summary", "")).strip()
                if dn:
                    display_name = dn[:60]
                    source = "ai"
                if sm:
                    ai_summary = sm[:160]
        except (json.JSONDecodeError, TypeError, OSError):
            pass
    base = prev or TaskJobStatus(task_id=cfg.task_id, rel_task=rel_task)
    write_task_job_status(
        cfg.primary,
        TaskJobStatus(
            task_id=cfg.task_id,
            rel_task=rel_task,
            stage=base.stage or "in-progress",
            owning_session_id=cfg.runner_id,
            worktree_path=str(cfg.current_wt_path or ""),
            branch=base.branch,
            task_title=label,
            display_name=display_name,
            ai_summary=ai_summary,
            display_name_source=source,
            naming_content_hash=nh,
            artifacts=list(base.artifacts) if base.artifacts else [],
        ),
    )


def _claim_task_on_primary(cfg: AutoFocusConfig, task_abs: Path, rel_task: str, logf: Path) -> str | None:
    try:
        tasks_lock_append(cfg.primary, task_abs)
    except OSError as exc:
        _append_diagnostic_log(logf, "CLAIM: tasks.lock append failed", str(exc))
        return None
    return rel_task


def _register_plan_file_artifact(cfg: AutoFocusConfig, plan_rel: str) -> None:
    if not cfg.task_id.strip() or not plan_rel.strip():
        return
    plan_path = Path(plan_rel)
    if not plan_path.is_file():
        return
    append_task_job_artifact(
        cfg.primary,
        cfg.task_id,
        {
            "source_abs": plan_path.resolve().as_posix(),
            "archive_name": plan_path.name,
        },
    )


def _archive_recorded_artifacts(cfg: AutoFocusConfig, wt_path: Path) -> None:
    st = read_task_job_status(cfg.primary, cfg.task_id)
    if st is None or not st.artifacts:
        return
    dest_root = sponte_tracked_task_artifacts_dir(cfg.primary, cfg.task_id)
    dest_root.mkdir(parents=True, exist_ok=True)
    for ent in st.artifacts:
        src_rel = (ent.get("source_rel") or "").strip()
        src_abs = (ent.get("source_abs") or "").strip()
        archive_name = (ent.get("archive_name") or "").strip()
        if not archive_name:
            continue
        if src_abs:
            src = Path(src_abs)
        elif src_rel:
            src = wt_path / src_rel
        else:
            continue
        if src.is_file():
            try:
                shutil.copy2(src, dest_root / archive_name)
            except OSError:
                pass


def _record_base(primary: Path, wt: Path, task_rel: str) -> None:
    ralph_data = ralph_data_dir(primary)
    ralph_data.mkdir(parents=True, exist_ok=True)
    code, out, _ = git(wt, "rev-parse", "HEAD")
    if code == 0:
        base_sha_file(primary).write_text(out.strip(), encoding="utf-8")
    base_task_file(primary).write_text(task_rel + "\n", encoding="utf-8")


def _auto_finalize_task_branch(primary: Path, wt: Path, rel_task: str) -> None:
    sha_path = readable_base_sha_file(primary)
    if not sha_path.is_file():
        return
    base_sha = sha_path.read_text(encoding="utf-8").strip()
    label = task_label(wt / rel_task)
    git(wt, "reset", "--soft", base_sha)
    code, out, _ = git(wt, "diff", "--cached", "--quiet")
    if code == 0:
        return
    subj = truncate_subject(label, prefix="ralph(sponte): ", max_total=50)
    git(
        wt,
        "-c",
        f"user.name={GIT_IDENTITY_NAME}",
        "-c",
        f"user.email={GIT_IDENTITY_EMAIL}",
        "commit",
        "-m",
        subj,
    )


def _resolve_primary_precheck_conflicts(
    cfg: AutoFocusConfig,
    logf: Path,
    wt_path: Path,
    br_name: str,
    main_ref: str,
    rel_task: str,
    plan_rel: str,
    implement_next: int,
    improve_i: int,
    improve_j: int,
    start_round: int,
) -> int:
    """
    Resolve merge conflicts on the primary checkout before Ralph merges the feature branch.
    Does not run ``git merge --abort`` on failure (unlike _resolve_merge_with_agent).
    """
    primary = cfg.primary
    r = start_round - 1
    while r < cfg.conflict_rounds_max:
        r += 1
        _persist(
            cfg,
            logf,
            wt_path,
            br_name,
            main_ref,
            rel_task,
            plan_rel,
            "PRIMARY_PREMERGE",
            implement_next,
            improve_i,
            improve_j,
            r,
        )
        _append_phase_log(logf, f"PRIMARY_PREMERGE_RESOLUTION_{r}")
        cfg.stats.merge_conflict_rounds += 1
        body = render_prompt("primary_precheck_merge_conflict", primary=cfg.primary, task_rel="", plan_rel="")
        rc = _run_non_task_phase_agent(
            cfg,
            cwd=primary,
            model=cfg.execute_model,
            prompt_body=body,
            logf=logf,
            label=f"PRIMARY_PREMERGE_{r}",
        )
        if rc != 0:
            return rc
        git(primary, "add", "-A")
        code_mh, _, _ = git(primary, *git_verify_ref_args("MERGE_HEAD"))
        if code_mh == 0:
            code2, _, _ = git(primary, *git_diff_cached_quiet_args())
            if code2 != 0:
                rc3, _, _ = git(
                    primary,
                    "-c",
                    f"user.name={GIT_IDENTITY_NAME}",
                    "-c",
                    f"user.email={GIT_IDENTITY_EMAIL}",
                    *git_commit_no_edit_args(),
                )
                if rc3 != 0:
                    _append_diagnostic_log(
                        logf,
                        "PRIMARY_PREMERGE: git commit --no-edit failed",
                        "Agent left the primary checkout with staged merge changes that could not be committed.",
                    )
                    return 1
        ps = primary_merge_precheck_state(primary)
        if ps.kind == PrimaryPrecheckKind.CLEAN:
            return 0
        if ps.kind == PrimaryPrecheckKind.REBASE_IN_PROGRESS:
            return 1
        if ps.kind == PrimaryPrecheckKind.OTHER_DIRTY:
            return 1
    return 1


def _merge_feature_to_main(primary: Path, branch: str, main_ref: str, logf: Path) -> bool:
    rc, _, e = git(primary, *git_checkout_branch_args(main_ref))
    with logf.open("a", encoding="utf-8") as lf:
        lf.write(e)
    if rc != 0:
        return False
    suffix = branch.split("/")[-1]
    msg = truncate_subject(f"merge {suffix}", prefix="ralph(sponte): ", max_total=50)
    rc, _, e = git(primary, *git_merge_feature_args(branch, msg))
    with logf.open("a", encoding="utf-8") as lf:
        lf.write(e)
    return rc == 0


def _resolve_merge_with_agent(
    cfg: AutoFocusConfig,
    logf: Path,
    branch: str,
    main_ref: str,
    start_round: int,
    wt_path: Path,
    rel_task: str,
    plan_rel: str,
    implement_next: int,
    improve_i: int,
    improve_j: int,
) -> int:
    r = start_round - 1
    primary = cfg.primary
    while r < cfg.conflict_rounds_max:
        r += 1
        body = render_prompt("merge_conflict", primary=cfg.primary, task_rel="", plan_rel="")
        _persist(
            cfg,
            logf,
            wt_path,
            branch,
            main_ref,
            rel_task,
            plan_rel,
            "MERGE_CONFLICT",
            implement_next,
            improve_i,
            improve_j,
            r,
        )
        _append_phase_log(logf, f"MERGE_CONFLICT_RESOLUTION_{r}")
        cfg.stats.merge_conflict_rounds += 1
        rc = _run_non_task_phase_agent(
            cfg,
            cwd=primary,
            model=cfg.execute_model,
            prompt_body=body,
            logf=logf,
            label=f"MERGE_CONFLICT_{r}",
        )
        if rc != 0:
            return rc
        code, _, _ = git(primary, *git_verify_ref_args("MERGE_HEAD"))
        if code == 0:
            git(primary, *git_add_all_args())
            code2, _, _ = git(primary, *git_diff_cached_quiet_args())
            if code2 != 0:
                rc3, _, _ = git(
                    primary,
                    "-c",
                    f"user.name={GIT_IDENTITY_NAME}",
                    "-c",
                    f"user.email={GIT_IDENTITY_EMAIL}",
                    *git_commit_no_edit_args(),
                )
                if rc3 == 0:
                    return 0
        git(primary, *git_merge_abort_args())
        git(primary, *git_checkout_branch_args(main_ref))
        if _merge_feature_to_main(primary, branch, main_ref, logf):
            return 0
    return 1


def _move_completed_on_primary(cfg: AutoFocusConfig, rel: str) -> None:
    primary = cfg.primary
    rel_norm = concrete_task_rel(primary, rel)
    p = primary / rel_norm
    if not p.is_file() or not _task_is_complete(primary, cfg.task_id, p):
        return
    prev = read_task_job_status(primary, cfg.task_id)
    name = Path(rel_norm).name
    rc_rm, _, _ = git(primary, "rm", "-f", "--ignore-unmatch", rel_norm)
    if rc_rm == 0:
        msg = truncate_subject(f"complete {name}", prefix="chore(tasks): ", max_total=50)
        git(
            primary,
            "-c",
            f"user.name={GIT_IDENTITY_NAME}",
            "-c",
            f"user.email={GIT_IDENTITY_EMAIL}",
            "commit",
            "-m",
            msg,
        )
    else:
        try:
            p.unlink()
        except OSError:
            pass
    task_still_on_disk = p.is_file()
    cleanup_pending = task_still_on_disk or (bool(prev.cleanup_pending) if prev else False)
    write_task_job_status(
        primary,
        TaskJobStatus(
            task_id=cfg.task_id,
            rel_task=rel_norm,
            stage="completed",
            owning_session_id="",
            worktree_path="",
            branch="",
            task_title=(prev.task_title if prev else task_label(p)),
            display_name=(prev.display_name if prev else ""),
            ai_summary=(prev.ai_summary if prev else ""),
            display_name_source=(prev.display_name_source if prev else ""),
            naming_content_hash=(prev.naming_content_hash if prev else ""),
            artifacts=list(prev.artifacts) if prev and prev.artifacts else [],
            completed=True,
            cleanup_pending=cleanup_pending,
        ),
    )
    try:
        tasks_lock_remove(primary, p.resolve())
    except OSError:
        pass
    if cleanup_pending:
        return
    job_dir = sponte_job_task_dir(primary, cfg.task_id)
    shutil.rmtree(job_dir, ignore_errors=True)
    if job_dir.is_dir():
        write_task_job_status(
            primary,
            TaskJobStatus(
                task_id=cfg.task_id,
                rel_task=rel_norm,
                stage="completed",
                owning_session_id="",
                worktree_path="",
                branch="",
                task_title=(prev.task_title if prev else task_label(p)),
                display_name=(prev.display_name if prev else ""),
                ai_summary=(prev.ai_summary if prev else ""),
                display_name_source=(prev.display_name_source if prev else ""),
                naming_content_hash=(prev.naming_content_hash if prev else ""),
                artifacts=list(prev.artifacts) if prev and prev.artifacts else [],
                completed=True,
                cleanup_pending=True,
            ),
        )
