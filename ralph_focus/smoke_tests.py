"""Lightweight checks for CI / `python3 ./.agents/ralph smoke`."""

from __future__ import annotations

import tempfile
from pathlib import Path

from rich.console import Console

from config.commands import VERIFY_COMMANDS, verify_commands_markdown
from config.defaults import NO_PROGRESS_LOOPS_MAX
from config.defaults import (
    LEGACY_RALPH_DATA_DIR,
    ROTATE_THRESHOLD_TOKENS,
    SPONTE_GUARDRAILS_PATH,
    SPONTE_PROGRESS_PATH,
    TASKS_DIR,
    WORKTREE_BASE_DIR,
)
from ralph_focus.contracts import FileSystemRunStateStore, FileTaskStore, get_harness
from ralph_focus.cycle import (
    derive_warn_threshold_tokens,
    phase_uses_plan_model,
    should_rotate_after_usage,
)
from ralph_focus.failure_detection import FailureKind, ProgressSnapshot, classify_agent_failure
from ralph_focus.interactive_setup import resolve_choice_index
from ralph_focus.phase_policy import phase_model_for, phase_uses_agent
from ralph_focus.primary_precheck import (
    PrimaryPrecheckKind,
    merge_precheck_classify_porcelain,
)
from ralph_focus.git_message import lint_commit_message
from ralph_focus.resume import ResumeState, clear_resume, load_resume, write_resume
from ralph_focus.stream_json import summarize_stream_file
from ralph_focus.lockfile import LockHeldError, acquire_lock, release_lock
from ralph_focus.paths import merge_into_branch_lock_path, plan_file_for_task, ralph_data_dir, ralph_lock_path, resume_file
from ralph_focus.ralph_session_lock import (
    clear_ralph_lock_matching_runner,
    finalize_ralph_lock_if_session_idle,
    read_ralph_lock,
    write_ralph_lock,
)
from ralph_focus.token_rotation import TokenRotationPolicy
from ralph_focus.tasks import (
    clear_task_cache,
    normalize_task_path,
    priority_task_paths,
    priority_task_paths_pending,
    select_task_from_priorities,
    task_has_pending,
    task_snapshot,
)
from ralph_focus.time_parse import format_seconds_human, parse_duration_to_seconds


def run_all(console: Console | None = None) -> None:
    c = console or Console(stderr=True)
    _test_parse_duration()
    _test_phase_model_ownership()
    _test_rotation_threshold_helpers()
    _test_stream_summarize()
    _test_stream_summarize_factory_completion()
    _test_git_message_lint()
    _test_resume_roundtrip()
    _test_resume_runner_partition()
    _test_ralph_session_lock_file()
    _test_merge_lock_path_and_lockfile()
    _test_tasks_helpers()
    _test_phase_policy()
    _test_token_rotation_policy()
    _test_failure_classification()
    _test_interactive_setup()
    _test_primary_precheck_classify()
    _test_contracts_boundary()
    c.print("[dim]smoke: all checks passed[/dim]")


def _test_parse_duration() -> None:
    assert parse_duration_to_seconds("3600") == 3600
    assert parse_duration_to_seconds("6h") == 6 * 3600
    assert parse_duration_to_seconds("1h30m") == 3600 + 30 * 60
    assert "6h" in format_seconds_human(6 * 3600)
    assert format_seconds_human(90) == "1m 30s"


def _test_phase_model_ownership() -> None:
    assert phase_uses_plan_model("PLAN") is True
    assert phase_uses_plan_model("IMPROVE_REVIEW") is True
    assert phase_uses_plan_model("VERIFY") is True
    assert phase_uses_plan_model("IMPLEMENT") is False
    assert phase_uses_plan_model("IMPROVE_EXECUTE") is False
    assert phase_uses_plan_model("MERGE_CONFLICT") is False


def _test_rotation_threshold_helpers() -> None:
    assert ROTATE_THRESHOLD_TOKENS > 0
    assert derive_warn_threshold_tokens(80_000) == 70_000
    assert should_rotate_after_usage({"input_tokens": 40_000, "output_tokens": 39_999}, 80_000) is False
    assert should_rotate_after_usage({"input_tokens": 40_000, "output_tokens": 40_000}, 80_000) is True
    assert should_rotate_after_usage({"total_tokens": 80_000}, 80_000) is True
    assert should_rotate_after_usage({"total_tokens": 80_000, "input_tokens": 1}, 80_000) is False
    assert should_rotate_after_usage({"total": 80_000}, 80_000) is True


def _test_stream_summarize() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"type":"result","duration_ms":1500,"usage":{"input_tokens":42,"output_tokens":7}}\n')
        name = f.name
    try:
        s = summarize_stream_file(Path(name))
        assert "duration_ms=1500" in s
        assert "input_tokens=42" in s
    finally:
        Path(name).unlink(missing_ok=True)


def _test_stream_summarize_factory_completion() -> None:
    """Factory `droid exec --output-format stream-json` ends with type=completion."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"type":"tool_call","toolName":"Execute"}\n')
        f.write(
            '{"type":"completion","finalText":"done","numTurns":2,"durationMs":3000}\n',
        )
        name = f.name
    try:
        s = summarize_stream_file(Path(name))
        assert "durationMs=3000" in s
    finally:
        Path(name).unlink(missing_ok=True)


def _test_git_message_lint() -> None:
    w = lint_commit_message("x" * 60)
    assert any("subject" in x for x in w.warnings)


def _test_resume_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        st = ResumeState(
            primary=str(root.resolve()),
            phase="IMPLEMENT",
            logf=str(root / "log"),
            wt_path=str(root / "wt"),
            branch="b",
            main_ref="main",
            rel_task=f"{TASKS_DIR}/x.md",
            plan_rel=str(plan_file_for_task(root, "x")),
            implement_next=2,
            improve_i=1,
            improve_j=0,
            conflict_next=1,
            cycles_done=0,
            agent_kind="cursor",
            plan_model="a",
            agent_model="b",
            session_deadline_epoch="9999999999",
        )
        write_resume(root, st)
        loaded = load_resume(root)
        assert loaded is not None
        assert loaded.phase == "IMPLEMENT"
        clear_resume(root)
        assert load_resume(root) is None


def _test_resume_runner_partition() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        st_a = ResumeState(
            primary=str(root.resolve()),
            phase="PLAN",
            logf=str(root / "log"),
            wt_path=str(root / "wt"),
            branch="b",
            main_ref="main",
            rel_task=f"{TASKS_DIR}/x.md",
            plan_rel=str(plan_file_for_task(root, "x")),
            implement_next=1,
            improve_i=1,
            improve_j=0,
            conflict_next=1,
            cycles_done=0,
            agent_kind="cursor",
            plan_model="a",
            agent_model="b",
            session_deadline_epoch="9999999999",
        )
        st_b = ResumeState(
            primary=str(root.resolve()),
            phase="IMPLEMENT",
            logf=str(root / "log2"),
            wt_path=str(root / "wt2"),
            branch="c",
            main_ref="main",
            rel_task=f"{TASKS_DIR}/y.md",
            plan_rel=str(plan_file_for_task(root, "y")),
            implement_next=2,
            improve_i=1,
            improve_j=0,
            conflict_next=1,
            cycles_done=0,
            agent_kind="cursor",
            plan_model="a",
            agent_model="b",
            session_deadline_epoch="9999999999",
        )
        write_resume(root, st_a, runner_id="lane-a")
        write_resume(root, st_b, runner_id="lane-b")
        path_a = resume_file(root, runner_id="lane-a")
        path_b = resume_file(root, runner_id="lane-b")
        assert "runners" in path_a.as_posix()
        assert path_a != path_b
        la = load_resume(root, runner_id="lane-a")
        lb = load_resume(root, runner_id="lane-b")
        assert la is not None and lb is not None
        assert la.phase == "PLAN"
        assert lb.phase == "IMPLEMENT"
        clear_resume(root, runner_id="lane-a")
        assert load_resume(root, runner_id="lane-a") is None
        assert load_resume(root, runner_id="lane-b") is not None


def _test_ralph_session_lock_file() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_ralph_lock(
            root,
            runner_id="rap-test123",
            session_cycle=2,
            resuming_this_cycle=False,
        )
        lp = ralph_lock_path(root)
        assert lp.is_file()
        data = read_ralph_lock(root)
        assert data is not None
        assert data.get("runner_id") == "rap-test123"
        assert data.get("session_cycle") == 2
        assert data.get("resuming_this_cycle") is False
        assert "resume_hint" in data
        finalize_ralph_lock_if_session_idle(root, "rap-test123")
        assert not lp.is_file()
        write_ralph_lock(
            root,
            runner_id="lane-x",
            session_cycle=1,
            resuming_this_cycle=True,
        )
        clear_ralph_lock_matching_runner(root, "lane-x")
        assert not ralph_lock_path(root).is_file()
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text('{"schema_version": 999}\n', encoding="utf-8")
        assert read_ralph_lock(root) is None


def _test_merge_lock_path_and_lockfile() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        mp = merge_into_branch_lock_path(root, "main")
        assert mp.name == "merge-into-main.lock"
        assert "locks" in mp.as_posix()
    with tempfile.TemporaryDirectory() as d:
        lp = Path(d) / "t.lock"
        lp.write_text("999999999\nstale\n", encoding="utf-8")
        acquire_lock(lp)
        release_lock(lp)
        assert not lp.is_file()
    with tempfile.TemporaryDirectory() as d:
        lp = Path(d) / "held.lock"
        acquire_lock(lp)
        try:
            acquire_lock(lp)
            raise AssertionError("expected LockHeldError")
        except LockHeldError:
            pass
        release_lock(lp)


def _test_tasks_helpers() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / TASKS_DIR / "backlog").mkdir(parents=True)
        f = root / TASKS_DIR / "backlog" / "t.md"
        f.write_text("- [ ] a\n", encoding="utf-8")
        clear_task_cache()
        assert task_has_pending(f)
        snap = task_snapshot(f)
        assert snap.pending == 1
        assert normalize_task_path(root, f"{TASKS_DIR}/backlog/t.md") == f
        assert normalize_task_path(root, ".tasks/backlog/t.md") == f
        pri = root / TASKS_DIR / "priorities.md"
        pri.write_text("1. [x](./backlog/t.md)\n", encoding="utf-8")
        paths = priority_task_paths(pri, root)
        assert paths and paths[0] == f
        assert select_task_from_priorities(pri, root) == f
        assert priority_task_paths_pending(pri, root) == [f]
        b = root / TASKS_DIR / "backlog" / "b.md"
        b.write_text("- [ ] b\n", encoding="utf-8")
        pri2 = root / TASKS_DIR / "priorities2.md"
        pri2.write_text(
            "- [a](./backlog/t.md)\n- [b](./backlog/b.md)\n",
            encoding="utf-8",
        )
        pend = priority_task_paths_pending(pri2, root)
        assert f in pend and b in pend
        f.write_text('task: "renamed"\n- [x] a\n', encoding="utf-8")
        snap2 = task_snapshot(f)
        assert snap2.label == "renamed"
        assert snap2.done == 1


def _test_phase_policy() -> None:
    assert phase_model_for("PLAN", plan_model="plan", execute_model="exec") == "plan"
    assert phase_model_for("IMPROVE", plan_model="plan", execute_model="exec") == "plan"
    assert phase_model_for("VERIFY", plan_model="plan", execute_model="exec") == "plan"
    assert phase_model_for("IMPLEMENT", plan_model="plan", execute_model="exec") == "exec"
    assert phase_uses_agent("MERGE") is False
    assert phase_uses_agent("MERGE_CONFLICT") is True


def _test_token_rotation_policy() -> None:
    policy = TokenRotationPolicy(rotate_threshold=80_000, warn_threshold=0)
    assert policy.warn_threshold == 70_000
    assert policy.classify(69_999) == "ok"
    assert policy.classify(70_000) == "warn"
    assert policy.classify(80_000) == "rotate"
    if VERIFY_COMMANDS:
        assert verify_commands_markdown().startswith("- `")
    else:
        assert verify_commands_markdown() == "- `(no verification commands configured)`"


def _test_failure_classification() -> None:
    transient = classify_agent_failure("agent failed", "HTTP 429 rate limit exceeded", no_progress_streak=0)
    assert transient.kind is FailureKind.TRANSIENT
    gutter = classify_agent_failure(
        "agent made no progress",
        "no files changed",
        no_progress_streak=NO_PROGRESS_LOOPS_MAX,
        before=ProgressSnapshot(pending_count=2, dirty=False, head="abc"),
        after=ProgressSnapshot(pending_count=2, dirty=False, head="abc"),
    )
    assert gutter.kind is FailureKind.GUTTER


def _test_interactive_setup() -> None:
    assert resolve_choice_index(choice_count=3, raw_index=2) == 1


def _test_primary_precheck_classify() -> None:
    r = merge_precheck_classify_porcelain("", merge_head=False)
    assert r.kind == PrimaryPrecheckKind.CLEAN

    r = merge_precheck_classify_porcelain("", merge_head=True)
    assert r.kind == PrimaryPrecheckKind.CONFLICT_DIRTY

    r = merge_precheck_classify_porcelain(" M apps/app/foo.ts\n", merge_head=False)
    assert r.kind == PrimaryPrecheckKind.OTHER_DIRTY

    r = merge_precheck_classify_porcelain(f"UU apps/app/foo.ts\n", merge_head=False)
    assert r.kind == PrimaryPrecheckKind.CONFLICT_DIRTY

    r = merge_precheck_classify_porcelain(f" M {LEGACY_RALPH_DATA_DIR}/logs/x\n", merge_head=False)
    assert r.kind == PrimaryPrecheckKind.CLEAN

    r = merge_precheck_classify_porcelain(
        f"?? {WORKTREE_BASE_DIR}/raf-demo\n?? {SPONTE_GUARDRAILS_PATH}\n?? {SPONTE_PROGRESS_PATH}\n",
        merge_head=False,
    )
    assert r.kind == PrimaryPrecheckKind.CLEAN

    r = merge_precheck_classify_porcelain("x", merge_head=False, status_failed=True)
    assert r.kind == PrimaryPrecheckKind.OTHER_DIRTY


def _test_contracts_boundary() -> None:
    cursor = get_harness("cursor")
    claude = get_harness("claude")
    assert cursor.capabilities.supports_stream_json is True
    assert cursor.capabilities.supports_metrics_output is True
    assert claude.capabilities.supports_stream_json is False
    assert claude.capabilities.supports_metrics_output is False

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        task_store = FileTaskStore()
        task = root / TASKS_DIR / "backlog" / "contract-smoke.md"
        task.parent.mkdir(parents=True, exist_ok=True)
        task.write_text("- [ ] boundary\n", encoding="utf-8")
        assert task_store.resolve_task(root, "backlog/contract-smoke.md") == task
        assert task_store.has_pending(task) is True

        run_state = FileSystemRunStateStore(root)
        assert run_state.state_root() == ralph_data_dir(root)
        assert run_state.resume_file(runner_id="smoke").name == "resume.state"


if __name__ == "__main__":
    run_all()
