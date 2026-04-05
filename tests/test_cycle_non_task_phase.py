from dataclasses import replace
from pathlib import Path

import pytest

from ralph_focus.contracts import AvailabilityReport, FailureContext, HarnessCapabilities, RunRequest, RunResult
from ralph_focus.cycle import AutoFocusConfig, _run_non_task_phase_agent
from ralph_focus.failure_detection import FailureKind, classify_agent_failure


class _DummyHarness:
    def __init__(
        self,
        *,
        harness_id: str = "dummy",
        rc: int,
        usage: dict[str, int],
        log_text: str = "",
        exc: OSError | None = None,
        capabilities: HarnessCapabilities | None = None,
        prepare_model_suffix: str = "",
    ) -> None:
        self.id = harness_id
        self.display_name = harness_id.title()
        self.capabilities = capabilities or HarnessCapabilities()
        self._rc = rc
        self._usage = usage
        self._log_text = log_text
        self._exc = exc
        self._prepare_model_suffix = prepare_model_suffix
        self.prepared_requests: list[RunRequest] = []
        self.run_requests: list[RunRequest] = []

    def availability(self) -> AvailabilityReport:
        return AvailabilityReport(available=True)

    def prepare(self, request: RunRequest) -> RunRequest:
        self.prepared_requests.append(request)
        if not self._prepare_model_suffix:
            return request
        return replace(request, model=f"{request.model}{self._prepare_model_suffix}")

    def run(self, request: RunRequest) -> RunResult:
        self.run_requests.append(request)
        if self._exc is not None:
            raise self._exc
        if self._log_text:
            request.log_file.write_text(self._log_text, encoding="utf-8")
        return RunResult(exit_code=self._rc, usage=self._usage)

    def classify_failure(self, context: FailureContext):
        return classify_agent_failure(
            context.summary,
            context.detail,
            no_progress_streak=context.no_progress_streak,
            before=context.before,
            after=context.after,
        )


def test_run_agent_uses_harness_capabilities_and_prepare(tmp_path: Path) -> None:
    harness = _DummyHarness(
        harness_id="cursor",
        rc=0,
        usage={"total_tokens": 5},
        capabilities=HarnessCapabilities(
            supports_stream_json=False,
            supports_tee_output=False,
            supports_metrics_output=False,
        ),
        prepare_model_suffix="-prepared",
    )
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=harness,
        plan_model="planner",
        execute_model="executor",
        progress="full",
    )
    logf = tmp_path / "run.log"

    rc = cfg._run_agent(tmp_path, "executor", "prompt", logf, "IMPLEMENT_1")

    assert rc == 0
    assert len(harness.prepared_requests) == 1
    assert len(harness.run_requests) == 1
    assert harness.prepared_requests[0].use_stream_json is False
    assert harness.prepared_requests[0].tee_output is False
    assert harness.prepared_requests[0].metrics_out is None
    assert harness.run_requests[0].model == "executor-prepared"


def test_non_task_phase_returns_rotate_when_threshold_reached(tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(rc=0, usage={"total_tokens": 80_000}),
        plan_model="planner",
        execute_model="executor",
    )
    logf = tmp_path / "run.log"

    rc = _run_non_task_phase_agent(
        cfg,
        cwd=tmp_path,
        model="executor",
        prompt_body="prompt",
        logf=logf,
        label="MERGE_CONFLICT_1",
    )

    assert rc == 3


def test_non_task_phase_classifies_failures(tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(rc=1, usage={}, log_text="HTTP 429 rate limit exceeded"),
        plan_model="planner",
        execute_model="executor",
    )
    logf = tmp_path / "run.log"

    rc = _run_non_task_phase_agent(
        cfg,
        cwd=tmp_path,
        model="executor",
        prompt_body="prompt",
        logf=logf,
        label="PRIMARY_PREMERGE_1",
    )

    assert rc == 1
    assert cfg.last_failure_kind is FailureKind.TRANSIENT


def test_non_task_phase_classifies_strategy_os_errors(tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(
            rc=1,
            usage={},
            exc=OSError(28, "No space left on device"),
        ),
        plan_model="planner",
        execute_model="executor",
    )
    logf = tmp_path / "run.log"

    rc = _run_non_task_phase_agent(
        cfg,
        cwd=tmp_path,
        model="executor",
        prompt_body="prompt",
        logf=logf,
        label="PRIMARY_PREMERGE_1",
    )

    assert rc == 1
    assert cfg.last_failure_kind is FailureKind.TRANSIENT
    assert "No space left on device" in cfg.last_failure_detail


def test_primary_premerge_returns_error_when_commit_no_edit_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import cycle
    from ralph_focus.primary_precheck import PrimaryPrecheckKind

    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(rc=0, usage={}),
        plan_model="planner",
        execute_model="executor",
    )

    def fake_git(_cwd: Path, *args: str) -> tuple[int, str, str]:
        if args == ("add", "-A"):
            return 0, "", ""
        if args == tuple(cycle.git_verify_ref_args("MERGE_HEAD")):
            return 0, "", ""
        if args == tuple(cycle.git_diff_cached_quiet_args()):
            return 1, "", ""
        if args[-2:] == ("commit", "--no-edit"):
            return 1, "", "commit failed"
        return 0, "", ""

    class _State:
        kind = PrimaryPrecheckKind.CONFLICT_DIRTY
        detail = "still conflicted"

    monkeypatch.setattr(cycle, "git", fake_git)
    monkeypatch.setattr(cycle, "primary_merge_precheck_state", lambda _primary: _State())
    monkeypatch.setattr(cycle, "substitute", lambda prompt, **_: prompt)
    monkeypatch.setattr(cycle, "load_prompt", lambda _name: "prompt")
    monkeypatch.setattr(cycle, "_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(cycle, "_append_phase_log", lambda *args, **kwargs: None)

    rc = cycle._resolve_primary_precheck_conflicts(
        cfg,
        tmp_path / "run.log",
        tmp_path,
        "branch",
        "main",
        ".agents/tasks/in-progress/example.md",
        ".agents/ralph/data/plan.md",
        1,
        1,
        0,
        1,
    )

    assert rc == 1
