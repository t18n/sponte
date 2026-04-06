from pathlib import Path

from typer.testing import CliRunner

from config.defaults import TASKS_DIR
from ralph_focus.resume import ResumeState
from ralph_focus.task_jobs import SessionJobStatus, TaskJobStatus, write_session_job_status, write_task_job_status
from ralph_focus.workspace_analytics import AnalyticsSummary


def _output(result) -> str:
    return result.stdout + result.stderr


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
            rel_task=f"{TASKS_DIR}/in-progress/demo.md",
            phase="IMPLEMENT",
            worktree_path=str(tmp_path / "wt-demo"),
            branch="ralph/wt-demo",
        ),
    )
    write_task_job_status(
        tmp_path,
        TaskJobStatus(
            task_id="demo-abc123",
            rel_task=f"{TASKS_DIR}/in-progress/demo.md",
            stage="in-progress",
            owning_session_id="rap-1111",
            worktree_path=str(tmp_path / "wt-demo"),
            branch="ralph/wt-demo",
            task_title="Demo task",
        ),
    )
    backlog = tmp_path / TASKS_DIR / "backlog"
    backlog.mkdir(parents=True, exist_ok=True)
    (backlog / "queued.md").write_text("task: queued\n\n- [ ] next\n", encoding="utf-8")

    runner = CliRunner()
    status_result = runner.invoke(cli.app, ["status"])
    session_current_result = runner.invoke(cli.app, ["session-current"])
    task_current_result = runner.invoke(cli.app, ["task-current"])
    session_show_result = runner.invoke(cli.app, ["session-show", "rap-1111"])
    task_show_result = runner.invoke(cli.app, ["task-show", "demo-abc123"])

    assert status_result.exit_code == 0
    assert "Active sessions (job index): 1" in _output(status_result)
    assert "Claimed tasks: 1" in _output(status_result)
    assert "Backlog tasks: 1" in _output(status_result)
    assert session_current_result.exit_code == 0
    assert "rap-1111" in _output(session_current_result)
    assert "demo-abc123" in _output(session_current_result)
    assert task_current_result.exit_code == 0
    assert "demo-abc123" in _output(task_current_result)
    assert "rap-1111" in _output(task_current_result)
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

    runner = CliRunner()
    result = runner.invoke(cli.app, ["stats"])

    assert result.exit_code == 0
    assert "sessions_started" in _output(result)
    assert "Recent events" in _output(result)
    assert "demo-abc123" in _output(result)


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
