"""Policy.merge_required=false must not consult primary merge precheck state."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config.defaults import RESUME_SCHEMA_VERSION
from ralph_focus.contracts import AvailabilityReport, FailureContext, HarnessCapabilities, RunRequest, RunResult
from ralph_focus.cycle import AutoFocusConfig, run_one_cycle
from ralph_focus.failure_detection import FailureKind, classify_agent_failure
from ralph_focus.resume import ResumeState


class _Harness:
    id = "test"
    display_name = "Test"
    capabilities = HarnessCapabilities()

    def availability(self) -> AvailabilityReport:
        return AvailabilityReport(available=True)

    def prepare(self, request: RunRequest) -> RunRequest:
        return request

    def run(self, request: RunRequest) -> RunResult:
        return RunResult(exit_code=0, usage={})

    def classify_failure(self, context: FailureContext):
        return classify_agent_failure(
            context.summary,
            context.detail,
            no_progress_streak=context.no_progress_streak,
            before=context.before,
            after=context.after,
        )


def test_resume_merge_skips_primary_merge_precheck_when_merge_optional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ralph_focus.cycle as c

    precheck = MagicMock(
        side_effect=AssertionError("primary_merge_precheck_state must not run when merge_required is false")
    )
    monkeypatch.setattr(c, "primary_merge_precheck_state", precheck)
    monkeypatch.setattr(c, "merge_phase_locked", lambda _p, _m: nullcontext())
    monkeypatch.setattr(c, "worktree_registered", lambda *_a, **_k: True)
    monkeypatch.setattr(c, "worktree_clean", lambda *_a, **_k: True)
    monkeypatch.setattr(c, "is_branch_merged_into", lambda *_a, **_k: False)
    monkeypatch.setattr(c, "git", lambda *_a, **_k: (0, "", ""))
    monkeypatch.setattr(c, "_move_completed_on_primary", lambda *a, **k: None)
    monkeypatch.setattr(c, "clear_resume", lambda *a, **k: None)
    monkeypatch.setattr(c, "_release_task_lock", lambda *a, **k: None)
    monkeypatch.setattr(c, "bump_summary", lambda *a, **k: None)
    monkeypatch.setattr(c, "emit_lifecycle_event", lambda *a, **k: None)

    wt = tmp_path / "wt"
    wt.mkdir()
    task_rel = ".sponte/tasks/in-progress/t.md"
    task_path = wt / task_rel
    task_path.parent.mkdir(parents=True)
    task_path.write_text("# Task\n\n- [x] one\n", encoding="utf-8")

    logf = tmp_path / "run.log"
    logf.write_text("", encoding="utf-8")
    plan_rel = tmp_path / "plans" / "t.md"
    plan_rel.parent.mkdir(parents=True)
    plan_rel.write_text("", encoding="utf-8")

    st = ResumeState(
        schema_version=RESUME_SCHEMA_VERSION,
        primary=str(tmp_path.resolve()),
        phase="MERGE",
        logf=str(logf),
        wt_path=str(wt),
        branch="ralph/wt-t",
        main_ref="main",
        rel_task=task_rel,
        plan_rel=str(plan_rel.resolve()),
        resume_runner_id="sess1",
        task_id="t-abc123",
        agent_kind="",
    )

    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_Harness(),
        plan_model="p",
        execute_model="e",
        progress="off",
        runner_id="sess1",
        merge_required=False,
        task_id="t-abc123",
    )

    rc = run_one_cycle(cfg, use_resume=True, resume_state=st)
    assert rc == 0
    precheck.assert_not_called()


def test_resume_merge_calls_primary_precheck_when_merge_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control: merge_required true must invoke primary_merge_precheck_state (twice: pre + final)."""
    import ralph_focus.cycle as c
    from ralph_focus.primary_precheck import PrimaryPrecheckKind, PrimaryPrecheckResult

    calls: list[object] = []

    def record_precheck(primary: Path) -> PrimaryPrecheckResult:
        calls.append(primary)
        return PrimaryPrecheckResult(kind=PrimaryPrecheckKind.CLEAN, detail="")

    def fake_git(_repo: object, *args: str) -> tuple[int, str, str]:
        if len(args) >= 4 and args[0] == "rev-parse" and args[3] == "MERGE_HEAD":
            return (1, "", "")
        return (0, "", "")

    monkeypatch.setattr(c, "primary_merge_precheck_state", record_precheck)
    monkeypatch.setattr(c, "merge_phase_locked", lambda _p, _m: nullcontext())
    monkeypatch.setattr(c, "worktree_registered", lambda *_a, **_k: True)
    monkeypatch.setattr(c, "worktree_clean", lambda *_a, **_k: True)
    monkeypatch.setattr(c, "is_branch_merged_into", lambda *_a, **_k: False)
    monkeypatch.setattr(c, "git", fake_git)
    monkeypatch.setattr(c, "_merge_feature_to_main", lambda *_a, **_k: True)
    monkeypatch.setattr(c, "_move_completed_on_primary", lambda *a, **k: None)
    monkeypatch.setattr(c, "clear_resume", lambda *a, **k: None)
    monkeypatch.setattr(c, "_release_task_lock", lambda *a, **k: None)
    monkeypatch.setattr(c, "bump_summary", lambda *a, **k: None)
    monkeypatch.setattr(c, "emit_lifecycle_event", lambda *a, **k: None)

    wt = tmp_path / "wt"
    wt.mkdir()
    task_rel = ".sponte/tasks/in-progress/t.md"
    task_path = wt / task_rel
    task_path.parent.mkdir(parents=True)
    task_path.write_text("# Task\n\n- [x] one\n", encoding="utf-8")

    logf = tmp_path / "run.log"
    logf.write_text("", encoding="utf-8")
    plan_rel = tmp_path / "plans" / "t.md"
    plan_rel.parent.mkdir(parents=True)
    plan_rel.write_text("", encoding="utf-8")

    st = ResumeState(
        schema_version=RESUME_SCHEMA_VERSION,
        primary=str(tmp_path.resolve()),
        phase="MERGE",
        logf=str(logf),
        wt_path=str(wt),
        branch="ralph/wt-t",
        main_ref="main",
        rel_task=task_rel,
        plan_rel=str(plan_rel.resolve()),
        resume_runner_id="sess1",
        task_id="t-abc123",
        agent_kind="",
    )

    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_Harness(),
        plan_model="p",
        execute_model="e",
        progress="off",
        runner_id="sess1",
        merge_required=True,
        task_id="t-abc123",
    )

    rc = run_one_cycle(cfg, use_resume=True, resume_state=st)
    assert rc == 0
    assert len(calls) >= 2
