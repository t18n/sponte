from pathlib import Path

from typer.testing import CliRunner

from config.defaults import TASKS_DIR
from ralph_focus.resume import ResumeState


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
        lambda _name: (_ for _ in ()).throw(AssertionError("cli should use get_harness")),
        raising=False,
    )
    monkeypatch.setattr(cli, "get_harness", lambda name: harness, raising=False)

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        seen["cfg"] = cfg
        seen["use_resume"] = use_resume
        seen["resume_state"] = resume_state
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            f"{TASKS_DIR}/backlog/example.md",
            "--once",
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert seen["use_resume"] is False
    assert seen["resume_state"] is None
    assert seen["cfg"].harness is harness
    assert seen["cfg"].runner_id == "rap-test1234"


def test_auto_focus_requires_explicit_task_or_resume(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should stop before preflight")))
    monkeypatch.setattr(cli, "get_harness", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should stop before harness lookup")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["agent", "--once"])

    assert result.exit_code != 0
    output = (result.stdout + result.stderr).lower()
    assert "requires a task path" in output
    assert "sponte task-plan" in output


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
        lambda *, agent, console, verbose: seen.setdefault("preflight_agent", agent),
    )
    monkeypatch.setattr(cli, "get_harness", lambda name: _Harness(name), raising=False)

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
            "--resume",
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
    monkeypatch.setattr(cli, "get_harness", lambda name: _Harness(name), raising=False)
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
            "--resume",
            "lane-a",
            "--no-allow-agent-pick",
        ],
    )

    assert result.exit_code == 0
    assert seen["allow_agent_pick"] is True
    assert seen["task_arg"] == f"{TASKS_DIR}/in-progress/resumed.md"


def test_auto_focus_complete_worktree_runs_single_resume_cycle(monkeypatch, tmp_path: Path) -> None:
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
    resume_state = ResumeState(
        primary=str(tmp_path.resolve()),
        agent_kind="cursor",
        plan_model="saved-plan",
        agent_model="saved-exec",
        wt_path=str(wt.resolve()),
    )
    cycles: list[bool] = []

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        cli,
        "resolve_runner_for_worktree",
        lambda _primary, _wt: ("gen-orphan", resume_state),
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
    monkeypatch.setattr(cli, "get_harness", lambda _name: _Harness(), raising=False)

    def fake_run_one_cycle(_cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        cycles.append(use_resume)
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--complete-worktree",
            str(wt),
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert cycles == [True]


def test_auto_focus_complete_worktree_ignores_saved_cycle_count_for_one_attempt(
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
    resume_state = ResumeState(
        primary=str(tmp_path.resolve()),
        agent_kind="cursor",
        plan_model="saved-plan",
        agent_model="saved-exec",
        wt_path=str(wt.resolve()),
        cycles_done=7,
    )
    seen: list[bool] = []

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        cli,
        "resolve_runner_for_worktree",
        lambda _primary, _wt: ("gen-orphan", resume_state),
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
    monkeypatch.setattr(cli, "get_harness", lambda _name: _Harness(), raising=False)

    def fake_run_one_cycle(_cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        seen.append(use_resume)
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--complete-worktree",
            str(wt),
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert seen == [True]


def test_auto_focus_complete_worktree_ignores_expired_saved_deadline(monkeypatch, tmp_path: Path) -> None:
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
    resume_state = ResumeState(
        primary=str(tmp_path.resolve()),
        agent_kind="cursor",
        plan_model="saved-plan",
        agent_model="saved-exec",
        wt_path=str(wt.resolve()),
        session_deadline_epoch="1",
    )
    seen: list[bool] = []

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(cli, "resolve_primary_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        cli,
        "resolve_runner_for_worktree",
        lambda _primary, _wt: ("gen-orphan", resume_state),
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
    monkeypatch.setattr(cli, "get_harness", lambda _name: _Harness(), raising=False)

    def fake_run_one_cycle(_cfg, *, use_resume: bool, resume_state=None, stop_after_plan: bool = False) -> int:
        seen.append(use_resume)
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--complete-worktree",
            str(wt),
            "--skip-preflight",
            "--agent",
            "cursor",
        ],
    )

    assert result.exit_code == 0
    assert seen == [True]


def test_auto_focus_complete_worktree_rejects_combine_resume(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "--complete-worktree",
            str(tmp_path / "wt"),
            "--resume",
            "x",
        ],
    )
    assert result.exit_code == 1
