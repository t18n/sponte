from pathlib import Path

from typer.testing import CliRunner

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

    monkeypatch.setattr(cli, "_ensure_repo", lambda: tmp_path)
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

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None) -> int:
        seen["cfg"] = cfg
        seen["use_resume"] = use_resume
        seen["resume_state"] = resume_state
        return 0

    monkeypatch.setattr(cli, "run_one_cycle", fake_run_one_cycle)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["auto-focus", "--once", "--skip-preflight", "--agent", "cursor"])

    assert result.exit_code == 0
    assert seen["use_resume"] is False
    assert seen["resume_state"] is None
    assert seen["cfg"].harness is harness
    assert seen["cfg"].runner_id == "rap-test1234"


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

    monkeypatch.setattr(cli, "_ensure_repo", lambda: tmp_path)
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

    def fake_run_one_cycle(cfg, *, use_resume: bool, resume_state=None) -> int:
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
            "auto-focus",
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
        task_arg=".agents/tasks/in-progress/resumed.md",
        allow_agent_pick="true",
    )
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, "_ensure_repo", lambda: tmp_path)
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
            "auto-focus",
            "--once",
            "--resume",
            "lane-a",
            "--no-allow-agent-pick",
        ],
    )

    assert result.exit_code == 0
    assert seen["allow_agent_pick"] is True
    assert seen["task_arg"] == ".agents/tasks/in-progress/resumed.md"
