from pathlib import Path

from typer.testing import CliRunner

from config.defaults import TASKS_DIR
from ralph_focus.resume import ResumeLoadFailureReason, ResumeState
from ralph_focus.task_jobs import SessionJobStatus, TaskJobStatus, write_session_job_status, write_task_job_status
from ralph_focus.workspace_analytics import AnalyticsSummary, harness_model_increment_keys


def _output(result) -> str:
    return result.stdout + result.stderr


def test_harness_model_increment_keys_dedupes_plan_execute() -> None:
    assert harness_model_increment_keys("cursor", "auto", "auto") == ["cursor:auto"]
    assert harness_model_increment_keys("cursor", "p", "e") == ["cursor:p", "cursor:e"]
    assert harness_model_increment_keys("", "a", "b") == []
    assert harness_model_increment_keys("c", "x", "") == ["c:x"]


def test_auto_focus_builds_runtime_config_with_harness(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    harness = _Harness()
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_effective_runner_id", lambda _runner_id: "rap-test1234")
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "get_strategy",
        lambda _p, _name: (_ for _ in ()).throw(AssertionError("cli should use resolve_harness")),
        raising=False,
    )
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, name: harness, raising=False)

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        seen["cfg"] = cfg
        seen["task_arg_at_cycle"] = cfg.task_arg
        seen["use_resume"] = use_resume
        seen["resume_state"] = resume_state
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    task_file = tmp_path / TASKS_DIR / "backlog" / "example.md"
    task_file.parent.mkdir(parents=True)
    task_file.touch()

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--once",
            "--skip-preflight",
            "--task",
            str(task_file),
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert seen["use_resume"] is False
    assert seen["resume_state"] is None
    assert seen["cfg"].harness is harness
    assert seen["cfg"].runner_id == "rap-test1234"
    assert seen["task_arg_at_cycle"] == f"{TASKS_DIR}/backlog/example.md"


def test_auto_focus_requires_explicit_task_or_resume(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should stop before preflight")))
    monkeypatch.setattr(cli, "resolve_harness", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should stop before harness lookup")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["agent", "--once"])

    assert result.exit_code != 0
    out = result.stdout + result.stderr
    assert "`--task`" in out
    assert "sponte task-plan" in out.lower()


def test_auto_focus_auto_allows_empty_task_path(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    harness = _Harness()
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_effective_runner_id", lambda _runner_id: "rap-test1234")
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "get_strategy",
        lambda _p, _name: (_ for _ in ()).throw(AssertionError("cli should use resolve_harness")),
        raising=False,
    )
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, name: harness, raising=False)

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        seen["cfg"] = cfg
        seen["use_resume"] = use_resume
        seen["resume_state"] = resume_state
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    (tmp_path / TASKS_DIR).mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--auto",
            "--once",
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert seen["use_resume"] is False
    assert seen["resume_state"] is None
    assert seen["cfg"].task_arg == ""
    assert seen["cfg"].allow_agent_pick is True


def test_auto_focus_auto_skips_on_fatal_and_continues(monkeypatch, tmp_path: Path) -> None:
    """With --auto, FATAL/GUTTER should not exit the process; pick the next task."""
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult
    from ralph_focus.failure_detection import FailureKind

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    harness = _Harness()
    calls: list[int] = []

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_effective_runner_id", lambda _runner_id: "rap-test1234")
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "get_strategy",
        lambda _p, _name: (_ for _ in ()).throw(AssertionError("cli should use resolve_harness")),
        raising=False,
    )
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, name: harness, raising=False)
    monkeypatch.setattr(cli, "load_resume", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda *_a, **_k: (None, ResumeLoadFailureReason.missing_file),
    )

    def fake_abandon(c, *, resume_hint=None) -> None:
        c.current_wt_path = None

    monkeypatch.setattr(cli, "abandon_auto_pick_cycle_on_failure", fake_abandon)

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        calls.append(len(calls))
        if len(calls) == 1:
            cfg.last_failure_kind = FailureKind.FATAL
            cfg.last_failure_detail = "plan failed"
            cfg.current_wt_path = tmp_path / "fake-wt"
            return 1
        return 2

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    (tmp_path / TASKS_DIR).mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--auto",
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 2
    assert "Skipping to next pending task" in (result.stdout + result.stderr)


def test_auto_focus_auto_skips_pre_persist_setup_failure_and_continues(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult
    from ralph_focus.failure_detection import FailureKind

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    harness = _Harness()
    calls: list[int] = []
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_effective_runner_id", lambda _runner_id: "rap-test1234")
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "get_strategy",
        lambda _p, _name: (_ for _ in ()).throw(AssertionError("cli should use resolve_harness")),
        raising=False,
    )
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, name: harness, raising=False)
    monkeypatch.setattr(cli, "load_resume", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda *_a, **_k: (None, ResumeLoadFailureReason.missing_file),
    )

    def fake_abandon(c, *, resume_hint=None) -> None:
        seen["resume_hint"] = resume_hint
        seen["failed_setup_branch"] = c.failed_setup_branch
        c.failed_setup_branch = ""
        c.current_wt_path = None

    monkeypatch.setattr(cli, "abandon_auto_pick_cycle_on_failure", fake_abandon)

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        calls.append(len(calls))
        if len(calls) == 1:
            cfg.last_failure_kind = FailureKind.FATAL
            cfg.last_failure_detail = "fatal: a branch named 'ralph/wt-t-example1234' already exists"
            cfg.failed_setup_branch = "ralph/wt-t-example1234"
            return 1
        return 2

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    (tmp_path / TASKS_DIR).mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--auto",
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 2
    assert seen["resume_hint"] is None
    assert seen["failed_setup_branch"] == "ralph/wt-t-example1234"
    assert "already exists" in _output(result)
    assert "Skipping to next pending task" in _output(result)


def test_auto_pick_exits_when_task_store_missing(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should stop before preflight")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["agent", "--auto", "--once"])

    assert result.exit_code == 1
    out = (result.stdout + result.stderr).lower()
    assert "no task store" in out
    assert "task-plan" in out


def test_auto_focus_resume_uses_saved_harness_and_models_for_preflight_and_config(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        def __init__(self, harness_id: str) -> None:
            self.id = harness_id
            self.display_name = harness_id.title()
            self.capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    resume_state = ResumeState(
        primary=str(tmp_path),
        agent_kind="claude",
        plan_model="saved-plan",
        agent_model="saved-exec",
    )
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "load_resume", lambda _primary, runner_id: resume_state)
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda *args, runner_id="default", **kwargs: (resume_state, None),
    )
    monkeypatch.setattr(
        cli,
            "run_preflight",
            lambda *, agent, console, verbose, workspace_root=None: seen.setdefault("preflight_agent", agent),
        )
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, name: _Harness(name), raising=False)

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        seen["cfg_harness_id"] = cfg.harness.id
        seen["cfg_plan_model"] = cfg.plan_model
        seen["cfg_execute_model"] = cfg.execute_model
        seen["use_resume"] = use_resume
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--once",
            "--resume-session",
            "lane-a",
            "--agent",
            "cursor",
            "--plan-model",
            "fresh-plan",
            "--execute-model",
            "fresh-exec",
        ],
    )

    assert result.exit_code == 0
    assert seen == {
        "preflight_agent": "claude",
        "cfg_harness_id": "claude",
        "cfg_plan_model": "saved-plan",
        "cfg_execute_model": "saved-exec",
        "use_resume": True,
    }


def test_auto_focus_resume_prints_restored_task_pick_settings(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        def __init__(self, harness_id: str) -> None:
            self.id = harness_id
            self.display_name = harness_id.title()
            self.capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    resume_state = ResumeState(
        primary=str(tmp_path),
        agent_kind="claude",
        plan_model="saved-plan",
        agent_model="saved-exec",
        task_arg=f"{TASKS_DIR}/in-progress/resumed.md",
        allow_agent_pick="true",
    )
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "load_resume", lambda _primary, runner_id: resume_state)
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda *args, runner_id="default", **kwargs: (resume_state, None),
    )
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, name: _Harness(name), raising=False)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(cli, "run_one_cycle", lambda *_args, **_kwargs: 0)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--once",
            "--resume-session",
            "lane-a",
            "--no-allow-agent-pick",
        ],
    )

    assert result.exit_code == 0
    assert seen["allow_agent_pick"] is True
    assert seen["task_arg"] == f"{TASKS_DIR}/in-progress/resumed.md"


def test_auto_focus_resume_task_runs_single_resume_cycle(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    wt = tmp_path / ".sponte" / "worktrees" / "orphan"
    wt.mkdir(parents=True)
    task_job_id = "orphan-task-id"
    resume_state = ResumeState(
        primary=str(tmp_path.resolve()),
        agent_kind="cursor",
        plan_model="saved-plan",
        agent_model="saved-exec",
        wt_path=str(wt.resolve()),
        task_id=task_job_id,
    )
    cycles: list[bool] = []

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        cli,
        "resolve_runner_for_task_id",
        lambda _primary, tid: ("gen-orphan", resume_state) if tid == task_job_id else None,
    )
    monkeypatch.setattr(
        cli,
        "load_resume",
        lambda primary, runner_id: resume_state if runner_id == "gen-orphan" else None,
    )
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda _p, runner_id: (
            (resume_state, None)
            if runner_id == "gen-orphan"
            else (None, ResumeLoadFailureReason.missing_file)
        ),
    )
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, _name: _Harness(), raising=False)

    def fake_run_one_cycle(_cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        cycles.append(use_resume)
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--resume-task",
            task_job_id,
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert cycles == [True]


def test_auto_focus_resume_task_ignores_saved_cycle_count_for_one_attempt(
    monkeypatch, tmp_path: Path
) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    wt = tmp_path / ".sponte" / "worktrees" / "orphan"
    wt.mkdir(parents=True)
    task_job_id = "orphan-task-id"
    resume_state = ResumeState(
        primary=str(tmp_path.resolve()),
        agent_kind="cursor",
        plan_model="saved-plan",
        agent_model="saved-exec",
        wt_path=str(wt.resolve()),
        cycles_done=7,
        task_id=task_job_id,
    )
    seen: list[bool] = []

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        cli,
        "resolve_runner_for_task_id",
        lambda _primary, tid: ("gen-orphan", resume_state) if tid == task_job_id else None,
    )
    monkeypatch.setattr(
        cli,
        "load_resume",
        lambda primary, runner_id: resume_state if runner_id == "gen-orphan" else None,
    )
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda _p, runner_id: (
            (resume_state, None)
            if runner_id == "gen-orphan"
            else (None, ResumeLoadFailureReason.missing_file)
        ),
    )
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, _name: _Harness(), raising=False)

    def fake_run_one_cycle(_cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        seen.append(use_resume)
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--resume-task",
            task_job_id,
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert seen == [True]


def test_auto_focus_resume_task_ignores_expired_saved_deadline(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    wt = tmp_path / ".sponte" / "worktrees" / "orphan"
    wt.mkdir(parents=True)
    task_job_id = "orphan-task-id"
    resume_state = ResumeState(
        primary=str(tmp_path.resolve()),
        agent_kind="cursor",
        plan_model="saved-plan",
        agent_model="saved-exec",
        wt_path=str(wt.resolve()),
        session_deadline_epoch="1",
        task_id=task_job_id,
    )
    seen: list[bool] = []

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        cli,
        "resolve_runner_for_task_id",
        lambda _primary, tid: ("gen-orphan", resume_state) if tid == task_job_id else None,
    )
    monkeypatch.setattr(
        cli,
        "load_resume",
        lambda primary, runner_id: resume_state if runner_id == "gen-orphan" else None,
    )
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda _p, runner_id: (
            (resume_state, None)
            if runner_id == "gen-orphan"
            else (None, ResumeLoadFailureReason.missing_file)
        ),
    )
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, _name: _Harness(), raising=False)

    def fake_run_one_cycle(_cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        seen.append(use_resume)
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--resume-task",
            task_job_id,
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert seen == [True]


def test_session_resume_reports_load_failure_reason(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda *_a, **_k: (None, ResumeLoadFailureReason.primary_mismatch),
    )

    runner = CliRunner()
    result = runner.invoke(cli.app, ["session-resume", "rap-test1234"])

    assert result.exit_code == 1
    assert "Nothing to resume" in _output(result)
    assert "primary_mismatch" in _output(result)


def test_auto_focus_prints_non_resume_hint_when_resume_missing(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        cfg.current_wt_path = tmp_path / ".sponte" / "worktrees" / "example"
        cfg.current_wt_path.mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_effective_runner_id", lambda _runner_id: "rap-test1234")
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, _name: _Harness(), raising=False)
    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda *_a, **_k: (None, ResumeLoadFailureReason.missing_file),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--once",
            "--skip-preflight",
            "--task",
            str(tmp_path / TASKS_DIR / "backlog" / "example.md"),
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert "Worktree left for inspection" in _output(result)
    assert "Session resume file is missing or invalid" in _output(result)
    assert "task-resume <task_id>" in _output(result)
    assert "sponte session-resume rap-test1234" not in _output(result)


def test_auto_focus_prints_session_and_task_resume_hints_when_worktree_left(
    monkeypatch, tmp_path: Path
) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        cfg.current_wt_path = tmp_path / ".sponte" / "worktrees" / "example"
        cfg.current_wt_path.mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_effective_runner_id", lambda _runner_id: "rap-test1234")
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, _name: _Harness(), raising=False)
    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)
    monkeypatch.setattr(
        cli,
        "load_resume_detailed",
        lambda *_a, **_k: (
            ResumeState(primary=str(tmp_path.resolve()), task_id="t-abc123"),
            None,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--once",
            "--skip-preflight",
            "--task",
            str(tmp_path / TASKS_DIR / "backlog" / "example.md"),
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    out = _output(result)
    assert "Worktree left for inspection" in out
    assert "Resume session with:" in out
    assert "sponte session-resume rap-test1234" in out
    assert "Resume task with:" in out
    assert "sponte task-resume" in out
    assert "t-abc123" in out


def test_auto_focus_resume_task_rejects_combine_resume_session(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--resume-task",
            "tid-1",
            "--resume-session",
            "x",
        ],
    )
    assert result.exit_code == 1


def test_task_resume_command_prepares_new_session_and_invokes_agent(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    seen: dict[str, object] = {}
    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "prepare_task_resume", lambda *_a, **_k: ("rap-new1234", ""))
    monkeypatch.setattr(
        cli,
        "_invoke_agent_minimal",
        lambda *, workspace, resume_session: seen.update(
            {"workspace": workspace, "resume_session": resume_session}
        ),
    )

    runner = CliRunner()
    result = runner.invoke(cli.app, ["task-resume", "demo-abc123"])

    assert result.exit_code == 0
    assert "rap-new1234" in _output(result)
    assert seen == {"workspace": None, "resume_session": "rap-new1234"}


def test_status_and_inspection_commands_render_job_index(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)

    write_session_job_status(
        tmp_path,
        SessionJobStatus(
            session_id="rap-1111",
            workspace_root=str(tmp_path.resolve()),
            active_task_id="demo-abc123",
            rel_task=f"{TASKS_DIR}/demo.md",
            phase="IMPLEMENT",
            worktree_path=str(tmp_path / "feat_demo-abc123"),
            branch="feat/demo-abc123",
        ),
    )
    write_task_job_status(
        tmp_path,
        TaskJobStatus(
            task_id="demo-abc123",
            rel_task=f"{TASKS_DIR}/demo.md",
            stage="in-progress",
            owning_session_id="rap-1111",
            worktree_path=str(tmp_path / "feat_demo-abc123"),
            branch="feat/demo-abc123",
            task_title="Demo task",
        ),
    )
    tasks_root = tmp_path / TASKS_DIR
    tasks_root.mkdir(parents=True, exist_ok=True)
    (tasks_root / "queued.md").write_text("task: queued\n\n- [ ] next\n", encoding="utf-8")

    runner = CliRunner()
    status_result = runner.invoke(cli.app, ["status"])
    session_current_result = runner.invoke(cli.app, ["session-current"])
    task_current_result = runner.invoke(cli.app, ["task-current"])
    session_show_result = runner.invoke(cli.app, ["session-show", "rap-1111"])
    task_show_result = runner.invoke(cli.app, ["task-show", "demo-abc123"])

    assert status_result.exit_code == 0
    assert "Active sessions (job index): 1" in _output(status_result)
    assert "Claimed tasks: 1" in _output(status_result)
    assert "Task files: 1" in _output(status_result)
    assert session_current_result.exit_code == 0
    assert "rap-1111" in _output(session_current_result)
    assert "demo-abc123" in _output(session_current_result)
    assert task_current_result.exit_code == 0
    assert "demo-abc123" in _output(task_current_result)
    assert "rap-1111" in _output(task_current_result)
    assert "Demo task" in _output(task_current_result)
    assert session_show_result.exit_code == 0
    assert "active_task_id" in _output(session_show_result)
    assert "demo-abc123" in _output(session_show_result)
    assert task_show_result.exit_code == 0
    assert "owning_session_id" in _output(task_show_result)
    assert "Demo task" in _output(task_show_result)


def test_stats_command_renders_summary_and_recent_events(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "git_primary_checkout_root", lambda *_a, **_k: tmp_path)
    monkeypatch.setattr(cli, "sponte_tasks_layout_valid", lambda *_p: True)
    monkeypatch.setattr(
        cli,
        "load_global_summary",
        lambda: AnalyticsSummary(
            sessions_started=5,
            tasks_completed=10,
            tasks_claimed=12,
            total_task_wall_seconds=5400.0,
            total_tokens=100_000,
            lines_added=400,
            lines_deleted=50,
            merges_completed=7,
            harness_counts={"cursor": 4},
            harness_model_counts={"cursor:auto": 17, "cursor:gpt-4": 2},
            workspace_slugs=["abc"],
            updated_at="2026-04-06T11:00:00Z",
        ),
    )
    monkeypatch.setattr(cli, "count_agent_sessions_from_locks", lambda: (1, 0, 1))
    monkeypatch.setattr(
        cli,
        "load_known_workspaces",
        lambda: [tmp_path, tmp_path / "other"],
    )
    monkeypatch.setattr(
        cli,
        "load_summary",
        lambda _primary: AnalyticsSummary(
            sessions_started=2,
            sessions_resumed=1,
            tasks_completed=3,
            tasks_cancelled=1,
            tasks_review_required=1,
            cleanup_repairs=2,
            merges_completed=1,
            harness_counts={"codex": 1},
            harness_model_counts={"codex:o1": 1},
            updated_at="2026-04-06T12:00:00Z",
        ),
    )
    monkeypatch.setattr(
        cli,
        "read_recent_events",
        lambda _primary, limit=12: [
            {
                "timestamp": "2026-04-06T12:00:00Z",
                "event": "task_completed",
                "outcome": "ok",
                "duration_sec": 12.5,
                "cycles": 4,
                "session_id": "rap-1111",
                "task_id": "demo-abc123",
            }
        ],
    )

    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.setenv("LINES", "40")
    runner = CliRunner()
    result = runner.invoke(cli.app, ["stats"])

    assert result.exit_code == 0
    out = _output(result)
    assert "Global" in out
    assert "Workspace count" in out
    assert "Session count" in out
    assert "Session active now" in out
    assert "Task finished count" in out
    assert "Total merges" in out
    assert "Harnesses" in out
    assert "cursor (4)" in out
    assert "Models" in out
    assert "cursor:auto (17)" in out
    assert "cursor:gpt-4 (2)" in out
    assert "Lock files (stale / total)" in out
    assert "This workspace" in out and tmp_path.name in out
    assert "codex (1)" in out
    assert "codex:o1 (1)" in out
    assert "Recent events" in out
    assert "demo-abc123" in out


def test_stats_global_only_without_workspace(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "git_primary_checkout_root", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "load_global_summary",
        lambda: AnalyticsSummary(
            sessions_started=1,
            tasks_completed=2,
            updated_at="2026-04-06T10:00:00Z",
        ),
    )
    monkeypatch.setattr(cli, "count_agent_sessions_from_locks", lambda: (0, 0, 0))
    monkeypatch.setattr(cli, "load_known_workspaces", lambda: [])

    runner = CliRunner()
    result = runner.invoke(cli.app, ["stats"])

    assert result.exit_code == 0
    out = _output(result)
    assert "Global" in out
    assert "Workspace count" in out
    assert "No Sponte workspace in cwd" in out


def test_agent_help_uses_session_language_for_resume_option() -> None:
    from ralph_focus import cli

    runner = CliRunner()
    result = runner.invoke(cli.app, ["agent", "--help"])

    assert result.exit_code == 0
    assert "SESSION_ID" in result.stdout
    assert "TASK_ID" in result.stdout
    assert "--resume-session" in result.stdout
    assert "--resume-task" in result.stdout
    assert "--task" in result.stdout
    assert "--auto" in result.stdout
    assert "plan model" in result.stdout.lower()
    assert "warn and skip" in result.stdout.lower()
    assert "refresh harness" in result.stdout.lower()
    assert "automatically" in result.stdout.lower()


def test_auto_focus_rotation_auto_resumes_same_session(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities(supports_automatic_context_refresh=True)

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    calls: list[bool] = []
    handoff_path = tmp_path / "rotation-handoff.md"
    handoff_path.write_text("# Rotation handoff\n", encoding="utf-8")

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_effective_runner_id", lambda _runner_id: "rap-test1234")
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, _name: _Harness(), raising=False)
    monkeypatch.setattr(cli, "_write_rotation_handoff", lambda **_kwargs: handoff_path)
    monkeypatch.setattr(cli, "_print_rotation_handoff_inline", lambda **_kwargs: None)

    def fake_run_one_cycle(_cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        calls.append(use_resume)
        return 3 if len(calls) == 1 else 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--once",
            "--skip-preflight",
            "--task",
            str(tmp_path / TASKS_DIR / "backlog" / "example.md"),
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert calls == [False, True]
    assert "sponte session-resume" not in _output(result)


def test_auto_focus_rotation_falls_back_to_manual_resume_when_harness_cannot_refresh(
    monkeypatch, tmp_path: Path
) -> None:
    from ralph_focus import cli
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult

    class _Harness:
        id = "custom"
        display_name = "Custom"
        capabilities = HarnessCapabilities(supports_automatic_context_refresh=False)

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=True)

        def prepare(self, request: RunRequest) -> RunRequest:
            return request

        def run(self, request: RunRequest) -> RunResult:
            return RunResult(exit_code=0, usage={})

    handoff_path = tmp_path / "rotation-handoff.md"
    handoff_path.write_text("# Rotation handoff\n", encoding="utf-8")

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "_effective_runner_id", lambda _runner_id: "rap-test1234")
    monkeypatch.setattr(cli, "_print_auto_focus_settings", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_print_session_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "write_ralph_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "finalize_ralph_lock_if_session_idle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_harness", lambda _p, _name: _Harness(), raising=False)
    monkeypatch.setattr(cli, "_write_rotation_handoff", lambda **_kwargs: handoff_path)
    monkeypatch.setattr(cli, "_print_rotation_handoff_inline", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "run_one_cycle", lambda *_args, **_kwargs: 3)
    monkeypatch.setattr(cli, "load_resume_detailed", lambda *_a, **_k: (ResumeState(primary=str(tmp_path.resolve())), None))

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--once",
            "--skip-preflight",
            "--task",
            str(tmp_path / TASKS_DIR / "backlog" / "example.md"),
            "--agent",
            "custom",
        ],
    )

    assert result.exit_code == 0
    assert "sponte session-resume" in _output(result)
