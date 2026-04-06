from dataclasses import replace
from pathlib import Path

import pytest

from config.defaults import LEGACY_TASKS_DIR, TASKS_DIR
from ralph_focus.run_events import RunEvent
from ralph_focus.contracts import AvailabilityReport, FailureContext, HarnessCapabilities, RunRequest, RunResult
from ralph_focus.cycle import AutoFocusConfig, _agent_pick_backlog_task, _run_non_task_phase_agent
from ralph_focus.paths import plan_file_for_task
from ralph_focus.failure_detection import FailureKind, classify_agent_failure
from ralph_focus.resume import ResumeState, load_resume, write_resume


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
        on_run=None,
    ) -> None:
        self.id = harness_id
        self.display_name = harness_id.title()
        self.capabilities = capabilities or HarnessCapabilities()
        self._rc = rc
        self._usage = usage
        self._log_text = log_text
        self._exc = exc
        self._prepare_model_suffix = prepare_model_suffix
        self._on_run = on_run
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
        if self._on_run is not None:
            self._on_run(request)
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
    assert harness.prepared_requests[0].watchdog is not None
    assert harness.prepared_requests[0].watchdog.stall_timeout_sec is not None
    assert harness.prepared_requests[0].watchdog.total_runtime_timeout_sec is not None
    assert harness.run_requests[0].model == "executor-prepared"


def test_run_agent_updates_phase_tokens_from_live_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import cycle

    token_totals: list[tuple[int | None, bool]] = []

    def fake_phase_bar(*_args, token_total=None, token_estimated=False, **_kwargs):
        token_totals.append((token_total, token_estimated))

    monkeypatch.setattr(cycle, "phase_bar", fake_phase_bar)
    monkeypatch.setattr(cycle, "step_done", lambda *_args, **_kwargs: None)

    def emit_live_usage(request: RunRequest) -> None:
        assert request.event_callback is not None
        request.event_callback(
            RunEvent(kind="usage", usage_delta={"input_tokens": 7, "output_tokens": 3}, estimated=False)
        )

    harness = _DummyHarness(
        harness_id="cursor",
        rc=0,
        usage={"input_tokens": 7, "output_tokens": 3},
        on_run=emit_live_usage,
    )
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=harness,
        plan_model="planner",
        execute_model="executor",
        progress="on",
    )

    rc = cfg._run_agent(tmp_path, "executor", "prompt", tmp_path / "run.log", "IMPLEMENT_1")

    assert rc == 0
    assert token_totals == [(0, False), (10, False)]


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


def test_non_task_phase_persists_live_token_totals_before_retry(tmp_path: Path) -> None:
    def emit_live_usage(request: RunRequest) -> None:
        assert request.event_callback is not None
        request.event_callback(
            RunEvent(kind="usage", usage_delta={"input_tokens": 7, "output_tokens": 3}, estimated=False)
        )
        request.log_file.write_text("sponte watchdog: cancelled run (stall_timeout)\n", encoding="utf-8")

    state = ResumeState(
        primary=str(tmp_path.resolve()),
        phase="IMPLEMENT",
        logf=str(tmp_path / "run.log"),
        wt_path=str(tmp_path / "wt"),
        rel_task=f"{TASKS_DIR}/in-progress/example.md",
        total_tokens=5,
    )
    write_resume(tmp_path, state, runner_id="lane-a")

    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(rc=1, usage={}, on_run=emit_live_usage),
        plan_model="planner",
        execute_model="executor",
        progress="on",
        runner_id="lane-a",
    )
    cfg.stats.add_tokens({"total_tokens": 5})

    rc = _run_non_task_phase_agent(
        cfg,
        cwd=tmp_path,
        model="executor",
        prompt_body="prompt",
        logf=tmp_path / "run.log",
        label="PRIMARY_PREMERGE_1",
    )

    loaded = load_resume(tmp_path, runner_id="lane-a")

    assert rc == 1
    assert loaded is not None
    assert loaded.total_tokens == 15
    assert cfg.last_failure_kind is FailureKind.TRANSIENT


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
    monkeypatch.setattr(cycle, "render_prompt", lambda _name, **_: "prompt")
    monkeypatch.setattr(cycle, "_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(cycle, "_append_phase_log", lambda *args, **kwargs: None)

    rc = cycle._resolve_primary_precheck_conflicts(
        cfg,
        tmp_path / "run.log",
        tmp_path,
        "branch",
        "main",
        f"{TASKS_DIR}/in-progress/example.md",
        str(plan_file_for_task(tmp_path, "plan")),
        1,
        1,
        0,
        1,
    )

    assert rc == 1


def test_move_completed_on_primary_moves_task_and_commits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import cycle
    from ralph_focus.tasks import task_id_from_resolved_path

    rel = f"{TASKS_DIR}/in-progress/example.md"
    task_path = tmp_path / rel
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text('task: "Example"\n- [x] done\n', encoding="utf-8")

    git_calls: list[tuple[Path, tuple[str, ...]]] = []

    def fake_git(cwd: Path, *args: str) -> tuple[int, str, str]:
        git_calls.append((cwd, args))
        return 0, "", ""

    monkeypatch.setattr(cycle, "git", fake_git)

    tid = task_id_from_resolved_path(task_path.resolve())
    cfg = cycle.AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(rc=0, usage={}),
        plan_model="p",
        execute_model="e",
        task_id=tid,
    )
    cycle._move_completed_on_primary(cfg, rel)

    assert git_calls[0] == (tmp_path, ("rm", "-f", "--ignore-unmatch", rel))
    assert git_calls[1][0] == tmp_path
    assert git_calls[1][1][-2:] == ("-m", "chore(tasks): complete example.md")


def test_claim_task_on_primary_appends_tasks_lock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import cycle
    from ralph_focus.tasks import task_id_from_resolved_path
    from ralph_focus.tasks_lock_registry import read_tasks_lock_paths

    logf = tmp_path / "claim.log"
    legacy_rel = f"{LEGACY_TASKS_DIR}/backlog/example.md"
    legacy_src = tmp_path / legacy_rel
    legacy_src.parent.mkdir(parents=True, exist_ok=True)
    legacy_src.write_text('task: "Example"\n- [ ] item\n', encoding="utf-8")
    tid = task_id_from_resolved_path(legacy_src.resolve())
    cfg = cycle.AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(rc=0, usage={}),
        plan_model="p",
        execute_model="e",
        task_id=tid,
    )
    dest = cycle._claim_task_on_primary(cfg, legacy_src, legacy_rel, logf)
    assert dest == legacy_rel
    locked = read_tasks_lock_paths(tmp_path)
    assert legacy_src.resolve() in locked


def test_auto_finalize_task_branch_reads_legacy_base_sha(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from config.defaults import LEGACY_RALPH_DATA_DIR
    from ralph_focus import cycle

    wt = tmp_path / "wt"
    wt.mkdir()
    task = wt / f"{TASKS_DIR}/in-progress/example.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text('task: "Example"\n- [x] done\n', encoding="utf-8")
    legacy_base = tmp_path / LEGACY_RALPH_DATA_DIR / "auto-focus-base-sha"
    legacy_base.parent.mkdir(parents=True, exist_ok=True)
    legacy_base.write_text("abc123\n", encoding="utf-8")

    git_calls: list[tuple[Path, tuple[str, ...]]] = []

    def fake_git(cwd: Path, *args: str) -> tuple[int, str, str]:
        git_calls.append((cwd, args))
        if args == ("diff", "--cached", "--quiet"):
            return 1, "", ""
        return 0, "", ""

    monkeypatch.setattr(cycle, "git", fake_git)

    cycle._auto_finalize_task_branch(tmp_path, wt, f"{TASKS_DIR}/in-progress/example.md")

    assert git_calls[0] == (wt, ("reset", "--soft", "abc123"))


def test_move_completed_on_primary_preserves_legacy_task_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import cycle
    from ralph_focus.tasks import task_id_from_resolved_path

    rel = f"{LEGACY_TASKS_DIR}/in-progress/example.md"
    task_path = tmp_path / rel
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text('task: "Example"\n- [x] done\n', encoding="utf-8")
    git_calls: list[tuple[Path, tuple[str, ...]]] = []

    def fake_git(cwd: Path, *args: str) -> tuple[int, str, str]:
        git_calls.append((cwd, args))
        return 0, "", ""

    monkeypatch.setattr(cycle, "git", fake_git)

    tid = task_id_from_resolved_path(task_path.resolve())
    cfg = cycle.AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(rc=0, usage={}),
        plan_model="p",
        execute_model="e",
        task_id=tid,
    )
    cycle._move_completed_on_primary(cfg, rel)

    assert git_calls[0] == (tmp_path, ("rm", "-f", "--ignore-unmatch", rel))


def test_agent_pick_backlog_task_resolves_legacy_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import cycle

    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(rc=0, usage={}),
        plan_model="planner",
        execute_model="executor",
    )
    nf = cycle.next_task_file(tmp_path)
    nf.parent.mkdir(parents=True, exist_ok=True)
    legacy_task = tmp_path / LEGACY_TASKS_DIR / "backlog" / "example.md"
    legacy_task.parent.mkdir(parents=True, exist_ok=True)
    legacy_task.write_text('task: "Example"\n- [ ] item\n', encoding="utf-8")

    monkeypatch.setattr(cycle, "_append_phase_log", lambda *_args, **_kwargs: None)

    models_seen: list[str] = []

    def fake_run_agent(_cwd: Path, model: str, _body: str, _logf: Path, _label: str) -> int:
        models_seen.append(model)
        nf.write_text(f"{LEGACY_TASKS_DIR}/backlog/example.md\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(cfg, "_run_agent", fake_run_agent)

    picked = _agent_pick_backlog_task(cfg)

    assert picked == legacy_task
    assert models_seen == ["planner"]
