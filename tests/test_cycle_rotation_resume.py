import shutil
from pathlib import Path

from ralph_focus.contracts import AvailabilityReport, FailureContext, HarnessCapabilities, RunRequest, RunResult
from ralph_focus.cycle import AutoFocusConfig, run_one_cycle
from ralph_focus.failure_detection import FailureKind, classify_agent_failure
from ralph_focus.paths import rotation_handoff_file
from ralph_focus.resume import ResumeState


class _DummyHarness:
    def __init__(self, harness_id: str = "dummy") -> None:
        self.id = harness_id
        self.display_name = harness_id.title()
        self.capabilities = HarnessCapabilities()

    def availability(self) -> AvailabilityReport:
        return AvailabilityReport(available=True)

    def prepare(self, request: RunRequest) -> RunRequest:
        return request

    def run(self, request: RunRequest) -> RunResult:
        raise AssertionError("harness.run should not be called directly in this test")

    def classify_failure(self, context: FailureContext):
        return classify_agent_failure(
            context.summary,
            context.detail,
            no_progress_streak=context.no_progress_streak,
            before=context.before,
            after=context.after,
        )


def _write_resume_task(tmp_path: Path) -> tuple[Path, Path, Path]:
    wt_path = tmp_path / "wt"
    wt_path.mkdir()
    logf = tmp_path / "run.log"
    logf.write_text("", encoding="utf-8")
    task = wt_path / ".agents" / "tasks" / "in-progress" / "example.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text('task: "Example"\n- [ ] item\n', encoding="utf-8")
    plan = wt_path / ".agents" / "ralph" / "data" / "plans" / "example.plan.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("", encoding="utf-8")
    return wt_path, logf, task


def _base_resume_state(tmp_path: Path, phase: str) -> ResumeState:
    wt_path, logf, _task = _write_resume_task(tmp_path)
    return ResumeState(
        primary=str(tmp_path.resolve()),
        phase=phase,
        logf=str(logf),
        wt_path=str(wt_path),
        branch="branch",
        main_ref="main",
        rel_task=".agents/tasks/in-progress/example.md",
        plan_rel=".agents/ralph/data/plans/example.plan.md",
        implement_next=1,
        improve_i=1,
        improve_j=0,
    )


def test_plan_rotation_advances_to_next_phase_before_exit(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(),
        plan_model="planner",
        execute_model="executor",
    )
    state = _base_resume_state(tmp_path, "PLAN")
    persisted: list[str] = []

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "worktree_registered", lambda _primary, _wt: True)
    monkeypatch.setattr(cycle, "_run_phase_agent", lambda *args, **kwargs: 3)
    monkeypatch.setattr(cycle, "_persist", lambda _cfg, *_args: persisted.append(_args[6]))

    rc = run_one_cycle(cfg, use_resume=True, resume_state=state)

    assert rc == 3
    assert persisted == ["IMPLEMENT"]


def test_implement_rotation_persists_next_round_before_exit(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(),
        plan_model="planner",
        execute_model="executor",
    )
    state = _base_resume_state(tmp_path, "IMPLEMENT")
    persisted: list[int] = []

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "worktree_registered", lambda _primary, _wt: True)
    monkeypatch.setattr(cycle, "_run_phase_agent", lambda *args, **kwargs: 3)
    monkeypatch.setattr(
        cycle,
        "_persist",
        lambda _cfg, _logf, _wt_path, _branch, _main_ref, _rel_task, _plan_rel, _phase, implement_next, *_rest: persisted.append(implement_next),
    )

    rc = run_one_cycle(cfg, use_resume=True, resume_state=state)

    assert rc == 3
    assert persisted == [1, 2]


def test_wrap_rotation_finalizes_and_advances_before_exit(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(),
        plan_model="planner",
        execute_model="executor",
    )
    state = _base_resume_state(tmp_path, "WRAP")
    finalized = False
    persisted: list[str] = []

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "worktree_registered", lambda _primary, _wt: True)
    monkeypatch.setattr(cycle, "_run_phase_agent", lambda *args, **kwargs: 3)
    monkeypatch.setattr(cycle, "_persist", lambda _cfg, *_args: persisted.append(_args[6]))

    def fake_finalize(_wt_path: Path, _rel_task: str) -> None:
        nonlocal finalized
        finalized = True

    monkeypatch.setattr(cycle, "_auto_finalize_task_branch", fake_finalize)

    rc = run_one_cycle(cfg, use_resume=True, resume_state=state)

    assert rc == 3
    assert finalized is True
    assert persisted == ["PRIORITIES"]


def test_resume_starts_with_fresh_rotation_budget(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(),
        plan_model="planner",
        execute_model="executor",
    )
    state = _base_resume_state(tmp_path, "PLAN")
    state.total_tokens = 80_000
    state.token_warning_emitted = "true"
    observed: dict[str, object] = {}

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "worktree_registered", lambda _primary, _wt: True)

    def fake_run_phase_agent(_cfg, *_args, **_kwargs) -> int:
        observed["total_tokens"] = _cfg.stats.total_tokens()
        observed["token_warning_emitted"] = _cfg.token_warning_emitted
        return 3

    monkeypatch.setattr(cycle, "_run_phase_agent", fake_run_phase_agent)
    monkeypatch.setattr(cycle, "_persist", lambda *args, **kwargs: None)

    rc = run_one_cycle(cfg, use_resume=True, resume_state=state)

    assert rc == 3
    assert observed == {
        "total_tokens": 0,
        "token_warning_emitted": False,
    }


def test_resume_prepends_rotation_handoff_to_first_prompt(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(),
        plan_model="planner",
        execute_model="executor",
        runner_id="rap-test1234",
    )
    state = _base_resume_state(tmp_path, "PLAN")
    handoff_path = rotation_handoff_file(tmp_path, runner_id="rap-test1234")
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        "Resume note: start from IMPLEMENT round 2.\n",
        encoding="utf-8",
    )
    prompts: list[str] = []

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "worktree_registered", lambda _primary, _wt: True)

    def fake_run_phase_agent(_cfg, *, prompt_name, rel_task, plan_rel, **_kwargs) -> int:
        prompts.append(_cfg._sub(prompt_name, rel_task, plan_rel))
        return 3

    monkeypatch.setattr(cycle, "_run_phase_agent", fake_run_phase_agent)
    monkeypatch.setattr(cycle, "_persist", lambda *args, **kwargs: None)

    rc = run_one_cycle(cfg, use_resume=True, resume_state=state)

    assert rc == 3
    assert prompts
    assert prompts[0].startswith("Resume note: start from IMPLEMENT round 2.")


def test_resume_restores_harness_from_saved_agent_kind(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness("initial"),
        plan_model="planner",
        execute_model="executor",
    )
    state = _base_resume_state(tmp_path, "PLAN")
    state.agent_kind = "restored"
    observed: dict[str, str] = {}

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "worktree_registered", lambda _primary, _wt: True)
    monkeypatch.setattr(
        cycle,
        "get_strategy",
        lambda _name: (_ for _ in ()).throw(AssertionError("resume should use get_harness")),
        raising=False,
    )
    monkeypatch.setattr(cycle, "get_harness", lambda name: _DummyHarness(name), raising=False)

    def fake_run_phase_agent(_cfg, *_args, **_kwargs) -> int:
        observed["harness_id"] = _cfg.harness.id
        return 3

    monkeypatch.setattr(cycle, "_run_phase_agent", fake_run_phase_agent)
    monkeypatch.setattr(cycle, "_persist", lambda *args, **kwargs: None)

    rc = run_one_cycle(cfg, use_resume=True, resume_state=state)

    assert rc == 3
    assert observed == {"harness_id": "restored"}


def test_resume_missing_state_sets_fatal_classification(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(),
        plan_model="planner",
        execute_model="executor",
        runner_id="lane-a",
    )

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "load_resume", lambda _primary, runner_id: None)

    rc = run_one_cycle(cfg, use_resume=True)

    assert rc == 1
    assert cfg.last_failure_kind is FailureKind.FATAL
    assert "No resume state found" in cfg.last_failure_detail
    assert "lane-a" in cfg.last_failure_detail


def test_resume_unregistered_worktree_sets_fatal_classification(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(),
        plan_model="planner",
        execute_model="executor",
    )
    state = _base_resume_state(tmp_path, "PLAN")

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "worktree_registered", lambda _primary, _wt: False)

    rc = run_one_cycle(cfg, use_resume=True, resume_state=state)

    assert rc == 1
    assert cfg.last_failure_kind is FailureKind.FATAL
    assert "not registered" in cfg.last_failure_detail
    assert state.wt_path in cfg.last_failure_detail


def test_resume_missing_worktree_directory_sets_fatal_classification(monkeypatch, tmp_path: Path) -> None:
    cfg = AutoFocusConfig(
        primary=tmp_path,
        harness=_DummyHarness(),
        plan_model="planner",
        execute_model="executor",
    )
    state = _base_resume_state(tmp_path, "PLAN")
    shutil.rmtree(state.wt_path)

    from ralph_focus import cycle

    monkeypatch.setattr(cycle, "worktree_registered", lambda _primary, _wt: True)

    rc = run_one_cycle(cfg, use_resume=True, resume_state=state)

    assert rc == 1
    assert cfg.last_failure_kind is FailureKind.FATAL
    assert "missing worktree directory" in cfg.last_failure_detail
    assert state.wt_path in cfg.last_failure_detail
