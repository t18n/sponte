"""One-ticket cycle: worktree, phases, merge to default branch (no push)."""

from __future__ import annotations

import re
import secrets
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
    GIT_IDENTITY_EMAIL,
    GIT_IDENTITY_NAME,
    IMPLEMENT_ROUNDS_MAX,
    IMPROVE_IMPLEMENT_MAX,
    NO_PROGRESS_LOOPS_MAX,
    RALPH_DATA_DIR,
    RESUME_SCHEMA_VERSION,
    ROTATE_THRESHOLD_TOKENS,
    ROTATE_WARN_THRESHOLD_TOKENS,
    SELECTION_LOCK_TIMEOUT_SEC,
    TASKS_DIR,
)
from ralph_focus.contracts import FailureContext, Harness, RunRequest, get_harness
from ralph_focus.failure_detection import FailureKind, ProgressSnapshot
from ralph_focus.phase_policy import PLANNER_PHASES, phase_model_for
from ralph_focus.git_message import truncate_subject
from ralph_focus.git_ops import default_branch_ref, git, worktree_registered
from ralph_focus.lockfile import release_lock
from ralph_focus.parallel_locks import (
    LockWaitTimeoutError,
    acquire_lock_blocking,
    merge_phase_locked,
    try_acquire_task_lock,
)
from ralph_focus.paths import (
    agent_pick_lock_path,
    auto_focus_logs_dir,
    base_sha_file,
    next_task_file,
    plan_file_for_task,
    plans_dir,
    ralph_data_dir,
    rotation_handoff_file,
    selection_lock_path,
    task_lock_path_for_rel,
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
from ralph_focus.prompts import load_prompt, substitute
from ralph_focus.resume import ResumeState, clear_resume, load_resume, write_resume
from ralph_focus.session_stats import SessionStats, _usage_rotation_tokens
from ralph_focus.token_rotation import TokenRotationPolicy, derive_warn_threshold
from ralph_focus.tasks import (
    count_checklist,
    normalize_task_path,
    priority_task_paths_pending,
    task_has_pending,
    task_label,
)

ProgressMode = Literal["off", "on", "full"]


def _slug_from_stem(stem: str) -> str:
    s = stem.lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    return s.strip("-") or "task"


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
    held_task_lock_path: Path | None = None
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
        self.last_agent_error_detail = ""
        if self.progress != "off" and use_json and self.harness.capabilities.supports_metrics_output:
            metrics = logf.parent / f".metrics-{secrets.token_hex(4)}.txt"
        request = self.harness.prepare(
            RunRequest(
                cwd=wt,
                model=model,
                prompt=prompt_body,
                log_file=logf,
                use_stream_json=use_json,
                tee_output=tee,
                metrics_out=metrics,
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
        self.stats.add_tokens(usage)
        wall = time.monotonic() - t0
        self.stats.add_step_wall(wall)
        summary = f"wall_s={wall:.1f}"
        if self.last_agent_error_detail:
            summary = f"{self.last_agent_error_detail}; {summary}"
        if metrics and metrics.is_file() and metrics.stat().st_size > 0:
            summary = metrics.read_text(encoding="utf-8", errors="replace")[:800] + f"; wall_s={wall:.1f}"
            metrics.unlink(missing_ok=True)
        if self.progress != "off":
            step_done(label, summary, model=model, token_total=self.stats.rotation_tokens())
        return rc

    def _sub(self, name: str, rel_task: str, plan_rel: str) -> str:
        prompt_body = substitute(
            load_prompt(name),
            task_rel=rel_task,
            plan_rel=plan_rel,
            verify_commands=verify_commands_markdown(),
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
    if cfg.held_task_lock_path is not None:
        release_lock(cfg.held_task_lock_path)
        cfg.held_task_lock_path = None


def _log_tail(logf: Path, *, lines: int = 80) -> str:
    if not logf.is_file():
        return ""
    raw_lines = logf.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(raw_lines[-lines:])


def _progress_snapshot(wt_path: Path, rel_task: str) -> ProgressSnapshot:
    pending, _done = count_checklist(wt_path / rel_task)
    dirty = not worktree_clean(wt_path)
    code, head, _ = git(wt_path, "rev-parse", "HEAD")
    return ProgressSnapshot(
        pending_count=pending,
        dirty=dirty,
        head=head.strip() if code == 0 else "",
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
) -> int:
    cfg.last_failure_kind = None
    cfg.last_failure_detail = ""
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
        or before.dirty != after.dirty
        or before.head != after.head
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


def run_one_cycle(
    cfg: AutoFocusConfig,
    *,
    use_resume: bool,
    resume_state: ResumeState | None = None,
) -> int:
    """
    Returns 0 success, 1 error, 2 no actionable task, 3 rotate session.
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
            cfg.harness = get_harness(st.agent_kind)
        cfg.allow_agent_pick = st.allow_agent_pick.lower() == "true"
        cfg.task_arg = st.task_arg
        cfg.cycles_done_entry = st.cycles_done
        cfg.max_cycles_str = st.max_cycles
        cfg.session_deadline_epoch = st.session_deadline_epoch or cfg.session_deadline_epoch
        cfg.current_wt_path = wt_path
        # Rotation is scoped to the current resumed process, not cumulative history.
        cfg.stats.total_token_count = 0
        cfg.stats.rotation_token_count = 0
        cfg.no_progress_loops = st.no_progress_loops
        cfg.token_warning_emitted = False
        handoff_path = rotation_handoff_file(primary, runner_id=cfg.runner_id)
        cfg.resume_handoff = handoff_path.read_text(encoding="utf-8", errors="replace") if handoff_path.is_file() else ""
        handoff_path.unlink(missing_ok=True)
        cfg.resume_handoff_pending = bool(cfg.resume_handoff.strip())
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
        stem = Path(task_rel).stem

        slug = _slug_from_stem(stem)
        shortid = secrets.token_hex(2)
        wt_path = primary / ".worktrees" / f"raf-{slug}-{shortid}"
        br_name = f"ralph/auto-focus-{slug}-{shortid}"
        main_ref = default_branch_ref(primary)

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

        _record_base(wt_path, task_rel)
        claimed = _claim_task_in_worktree(wt_path, task_rel, logf)
        if claimed is None:
            _release_task_lock(cfg)
            return 1
        rel_task = claimed
        plan_rel = plan_file_for_task(wt_path, Path(rel_task).stem).relative_to(wt_path).as_posix()
        plans_dir(wt_path).mkdir(parents=True, exist_ok=True)

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
        )
        if rc == 1:
            return rc
        phase = "IMPLEMENT"
        implement_next = 1
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
        if rc == 3:
            return 3

    # IMPLEMENT
    if phase == "IMPLEMENT":
        n = implement_next - 1
        while task_has_pending(wt_path / rel_task) and n < cfg.implement_rounds_max:
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
            )
            if rc == 1:
                return rc
            implement_next = n + 1
            _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
            if rc == 3:
                return 3
        if task_has_pending(wt_path / rel_task):
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
                )
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
                )
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
        phase = "FOLLOWUP"
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)

    if phase == "FOLLOWUP":
        _append_phase_log(logf, "FOLLOWUP_TICKETS")
        rc = _run_phase_agent(
            cfg,
            phase="FOLLOWUP",
            prompt_name="followup_tickets",
            wt_path=wt_path,
            rel_task=rel_task,
            plan_rel=plan_rel,
            logf=logf,
            label="FOLLOWUP_TICKETS",
        )
        if rc == 1:
            return rc
        phase = "WRAP"
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
        if rc == 3:
            return 3

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
        )
        if rc == 1:
            return rc
        _auto_finalize_task_branch(wt_path, rel_task)
        phase = "PRIORITIES"
        _persist(cfg, logf, wt_path, br_name, main_ref, rel_task, plan_rel, phase, implement_next, improve_i, improve_j, conflict_next)
        if rc == 3:
            return 3

    if phase == "PRIORITIES":
        _append_phase_log(logf, "PRIORITIES")
        rc = _run_phase_agent(
            cfg,
            phase="PRIORITIES",
            prompt_name="priorities",
            wt_path=wt_path,
            rel_task=rel_task,
            plan_rel=plan_rel,
            logf=logf,
            label="PRIORITIES",
        )
        if rc == 1:
            return rc
        if not _commit_worktree_pending_if_dirty(wt_path, logf, "priorities after auto-focus"):
            return 1
        phase = "VERIFY"
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
        )
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
            with merge_phase_locked(primary, main_ref):
                # Resume at MERGE skips PRIORITIES (and its post-phase commit). Any dirty worktree
                # would block merge — commit pending changes here too.
                merge_dirty_before = not worktree_clean(wt_path)
                if merge_dirty_before:
                    _append_phase_log(logf, "PRE_MERGE_COMMIT")
                    if not _commit_worktree_pending_if_dirty(wt_path, logf, "pre-merge auto-focus"):
                        merge_precheck_failed(
                            "Could not commit pending worktree changes before merge.",
                            "See run log (AUTO_COMMIT sections). Fix git state in the worktree, then retry with --resume RUNNER_ID.",
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
                        "Merge precheck: primary not clean (outside Ralph data dir)",
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
                                "See run log (PRIMARY_PREMERGE sections). Fix git state on the primary checkout, then retry with --resume RUNNER_ID.",
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
                            f"Primary has local changes outside {RALPH_DATA_DIR}/; commit or discard them, then retry.",
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
                        "then retry with --resume RUNNER_ID."
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

                _append_phase_log(logf, f"MERGE_TO_{main_ref}")
                feature_already_merged = is_branch_merged_into(primary, br_name, main_ref)
                if feature_already_merged:
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

                rc_rm, _, _ = git(primary, "worktree", "remove", str(wt_path))
                if rc_rm != 0 or wt_path.exists():
                    git(primary, "worktree", "remove", "-f", str(wt_path))
                git(primary, "branch", "-d", br_name)
                clear_resume(
                    primary,
                    runner_id=cfg.runner_id,
                )
                _move_completed_on_primary(primary, rel_task)
                _release_task_lock(cfg)
                cfg.stats.cycles_completed += 1
                cfg.current_wt_path = None
                return 0
        except LockWaitTimeoutError as e:
            _append_diagnostic_log(
                logf,
                f"MERGE: timed out waiting for merge-into-{main_ref} lock on primary",
                str(e),
            )
            merge_precheck_failed(
                f"Another Ralph runner is merging into local `{main_ref}` (or holding that merge lock) for too long.",
                "Wait and retry with --resume RUNNER_ID, or adjust RALPH_MERGE_LOCK_TIMEOUT_SEC.",
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
    )
    write_resume(
        cfg.primary,
        st,
        runner_id=cfg.runner_id,
    )


def _select_next_task_abs(cfg: AutoFocusConfig) -> tuple[int, Path | None]:
    primary = cfg.primary

    def _take_task_lock(task_abs: Path) -> bool:
        rel = task_abs.relative_to(primary).as_posix()
        lp = task_lock_path_for_rel(primary, rel)
        if not try_acquire_task_lock(lp):
            return False
        cfg.held_task_lock_path = lp
        return True

    if cfg.task_arg:
        p = normalize_task_path(primary, cfg.task_arg)
        if not p.is_file():
            return (1, None)
        if not task_has_pending(p):
            return (1, None)
        if not _take_task_lock(p):
            return (2, None)
        return (0, p)

    pri_file = primary / TASKS_DIR / "priorities.md"
    sel_lp = selection_lock_path(primary)
    try:
        acquire_lock_blocking(sel_lp, timeout_sec=SELECTION_LOCK_TIMEOUT_SEC)
    except LockWaitTimeoutError:
        return (1, None)
    try:
        for p in priority_task_paths_pending(pri_file, primary):
            if _take_task_lock(p):
                return (0, p)
    finally:
        release_lock(sel_lp)

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
        if not _take_task_lock(picked):
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
    body = load_prompt("agent_pick_task")
    _append_phase_log(logf, "AGENT_PICK_TASK")
    if cfg._run_agent(primary, cfg.execute_model, body, logf, "AGENT_PICK_TASK") != 0:
        return None
    if not nf.is_file():
        return None
    line = nf.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
    line = line.removeprefix("./")
    if line.startswith(".tasks/"):
        line = f"{TASKS_DIR}/{line.removeprefix('.tasks/')}"
    if not line.startswith(f"{TASKS_DIR}/backlog/"):
        return None
    abs_p = primary / line
    if not abs_p.is_file() or not task_has_pending(abs_p):
        return None
    return abs_p


def _record_base(wt: Path, task_rel: str) -> None:
    ralph_data = ralph_data_dir(wt)
    ralph_data.mkdir(parents=True, exist_ok=True)
    code, out, _ = git(wt, "rev-parse", "HEAD")
    if code == 0:
        (ralph_data / "auto-focus-base-sha").write_text(out.strip(), encoding="utf-8")
    (ralph_data / "auto-focus-base-task").write_text(task_rel + "\n", encoding="utf-8")


def _claim_task_in_worktree(wt: Path, rel: str, logf: Path) -> str | None:
    if rel.startswith(".tasks/"):
        rel = f"{TASKS_DIR}/{rel.removeprefix('.tasks/')}"
    backlog_p = f"{TASKS_DIR}/backlog/"
    if not rel.startswith(backlog_p):
        return rel
    name = Path(rel).name
    dest = f"{TASKS_DIR}/in-progress/{name}"
    (wt / TASKS_DIR / "in-progress").mkdir(parents=True, exist_ok=True)
    src = wt / rel
    if not src.is_file():
        return None
    rc, _, err = git(wt, "mv", rel, dest)
    if rc != 0:
        with logf.open("a", encoding="utf-8") as lf:
            lf.write(err)
        return None
    msg = truncate_subject(f"claim {name}", prefix="chore(tasks): ", max_total=50)
    git(
        wt,
        "-c",
        f"user.name={GIT_IDENTITY_NAME}",
        "-c",
        f"user.email={GIT_IDENTITY_EMAIL}",
        "commit",
        "-m",
        msg,
    )
    return dest


def _auto_finalize_task_branch(wt: Path, rel_task: str) -> None:
    sha_path = base_sha_file(wt)
    if not sha_path.is_file():
        return
    base_sha = sha_path.read_text(encoding="utf-8").strip()
    label = task_label(wt / rel_task)
    git(wt, "reset", "--soft", base_sha)
    code, out, _ = git(wt, "diff", "--cached", "--quiet")
    if code == 0:
        return
    subj = truncate_subject(label, prefix="ralph(auto-focus): ", max_total=50)
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
        body = substitute(load_prompt("primary_precheck_merge_conflict"), task_rel="", plan_rel="")
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
    msg = truncate_subject(f"merge {suffix}", prefix="ralph(auto-focus): ", max_total=50)
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
        body = substitute(load_prompt("merge_conflict"), task_rel="", plan_rel="")
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


def _move_completed_on_primary(primary: Path, rel: str) -> None:
    if rel.startswith(".tasks/"):
        rel = f"{TASKS_DIR}/{rel.removeprefix('.tasks/')}"
    in_p = f"{TASKS_DIR}/in-progress/"
    if not rel.startswith(in_p):
        return
    p = primary / rel
    if not p.is_file() or task_has_pending(p):
        return
    name = Path(rel).name
    dest = f"{TASKS_DIR}/completed/{name}"
    (primary / TASKS_DIR / "completed").mkdir(parents=True, exist_ok=True)
    git(primary, "mv", rel, dest)
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
