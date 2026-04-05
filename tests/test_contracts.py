from pathlib import Path

from ralph_focus.failure_detection import FailureKind, ProgressSnapshot


class DummyStrategy:
    id = "dummy"

    def __init__(self, *, errors: list[str] | None = None) -> None:
        self.errors = errors or []
        self.calls: list[tuple] = []

    def check_available(self) -> list[str]:
        return list(self.errors)

    def run(
        self,
        cwd: Path,
        model: str,
        prompt: str,
        log_file: Path,
        *,
        use_stream_json: bool,
        tee: bool,
        metrics_out: Path | None,
    ) -> tuple[int, dict[str, int]]:
        self.calls.append((cwd, model, prompt, log_file, use_stream_json, tee, metrics_out))
        return 7, {"input_tokens": 11, "output_tokens": 3}


def test_strategy_harness_adapter_exposes_stable_harness_surface(tmp_path: Path) -> None:
    from ralph_focus.contracts import (
        RunRequest,
        RunResult,
        StrategyHarnessAdapter,
    )

    strategy = DummyStrategy()
    harness = StrategyHarnessAdapter(strategy)
    request = RunRequest(
        cwd=tmp_path,
        model="auto",
        prompt="hello",
        log_file=tmp_path / "run.log",
        use_stream_json=True,
        tee_output=True,
        metrics_out=tmp_path / "metrics.txt",
    )

    availability = harness.availability()
    prepared = harness.prepare(request)
    result = harness.run(prepared)

    assert harness.id == "dummy"
    assert harness.display_name == "Dummy"
    assert availability.available is True
    assert availability.problems == ()
    assert harness.capabilities.supports_stream_json is False
    assert harness.capabilities.supports_tee_output is True
    assert harness.capabilities.supports_metrics_output is False
    assert prepared == request
    assert result == RunResult(exit_code=7, usage={"input_tokens": 11, "output_tokens": 3})
    assert strategy.calls == [
        (
            tmp_path,
            "auto",
            "hello",
            tmp_path / "run.log",
            True,
            True,
            tmp_path / "metrics.txt",
        )
    ]


def test_strategy_harness_adapter_reports_unavailable_problems() -> None:
    from ralph_focus.contracts import StrategyHarnessAdapter

    harness = StrategyHarnessAdapter(DummyStrategy(errors=["missing binary"]))

    availability = harness.availability()

    assert availability.available is False
    assert availability.problems == ("missing binary",)


def test_strategy_harness_adapter_classifies_failures_with_existing_logic() -> None:
    from ralph_focus.contracts import FailureContext, StrategyHarnessAdapter

    harness = StrategyHarnessAdapter(DummyStrategy())

    classification = harness.classify_failure(
        FailureContext(
            summary="run failed",
            detail="request timed out",
            no_progress_streak=0,
            before=ProgressSnapshot(pending_count=2, dirty=False, head="abc"),
            after=ProgressSnapshot(pending_count=2, dirty=False, head="abc"),
        )
    )

    assert classification.kind is FailureKind.TRANSIENT


def test_real_strategy_harness_capabilities_match_backend_support() -> None:
    from ralph_focus.contracts import get_harness

    cursor = get_harness("cursor")
    droid = get_harness("droid")
    claude = get_harness("claude")
    codex = get_harness("codex")
    amp = get_harness("amp")
    oz = get_harness("oz")

    assert cursor.capabilities.supports_stream_json is True
    assert cursor.capabilities.supports_metrics_output is True
    assert droid.capabilities.supports_stream_json is True
    assert droid.capabilities.supports_metrics_output is True
    assert claude.capabilities.supports_stream_json is False
    assert claude.capabilities.supports_metrics_output is False
    assert codex.capabilities.supports_stream_json is False
    assert codex.capabilities.supports_metrics_output is False
    assert amp.capabilities.supports_stream_json is False
    assert amp.capabilities.supports_metrics_output is False
    assert oz.capabilities.supports_stream_json is False
    assert oz.capabilities.supports_metrics_output is False


def test_get_harness_adapts_existing_strategy_lookup(monkeypatch) -> None:
    from ralph_focus import contracts

    monkeypatch.setattr(contracts, "get_strategy", lambda name: DummyStrategy() if name == "dummy" else None)

    harness = contracts.get_harness("dummy")

    assert harness.id == "dummy"
    assert harness.display_name == "Dummy"


def test_unknown_strategy_capabilities_fail_closed() -> None:
    from ralph_focus.contracts import harness_capabilities_for_strategy

    capabilities = harness_capabilities_for_strategy("future-backend")

    assert capabilities.supports_stream_json is False
    assert capabilities.supports_metrics_output is False


def test_file_task_store_wraps_existing_task_helpers(tmp_path: Path) -> None:
    from config.defaults import TASKS_DIR
    from ralph_focus.contracts import FileTaskStore

    repo = tmp_path
    task = repo / TASKS_DIR / "backlog" / "demo.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text('task: "Demo"\n- [ ] one\n- [x] two\n', encoding="utf-8")
    priorities = repo / TASKS_DIR / "priorities.md"
    priorities.parent.mkdir(parents=True, exist_ok=True)
    priorities.write_text("- [Demo](./backlog/demo.md)\n", encoding="utf-8")

    store = FileTaskStore()

    assert store.resolve_task(repo, "backlog/demo.md") == task
    assert store.priority_tasks(repo) == [task]
    assert store.task_snapshot(task).label == "Demo"
    assert store.task_snapshot(task).pending == 1
    assert store.task_snapshot(task).done == 1
    assert store.has_pending(task) is True


def test_project_workspace_wraps_git_helpers(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus.contracts import RepoProjectWorkspace

    seen: dict[str, Path] = {}

    def fake_trunk(primary: Path, *, cli_override: str | None) -> str:
        seen["default_branch"] = primary
        return "main"

    def fake_registered(root: Path, wt: Path) -> bool:
        seen["registered_root"] = root
        seen["registered_wt"] = wt
        return True

    monkeypatch.setattr(
        "ralph_focus.workspace_resolve.resolve_trunk_branch_ref",
        fake_trunk,
    )
    monkeypatch.setattr("ralph_focus.contracts.worktree_registered", fake_registered)

    workspace = RepoProjectWorkspace(tmp_path)
    from config.defaults import WORKTREE_BASE_DIR

    wt = tmp_path / WORKTREE_BASE_DIR / "demo"

    assert workspace.root == tmp_path
    assert workspace.default_branch() == "main"
    assert workspace.is_worktree_registered(wt) is True
    assert seen == {
        "default_branch": tmp_path,
        "registered_root": tmp_path,
        "registered_wt": wt,
    }


def test_run_state_store_uses_app_state_path_conventions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "sponte-app-state"))
    from ralph_focus.app_state_paths import workspace_runtime_root
    from ralph_focus.contracts import FileSystemRunStateStore

    store = FileSystemRunStateStore(tmp_path)
    state_root = workspace_runtime_root(tmp_path)

    assert store.state_root() == state_root
    assert store.logs_dir(runner_id="lane-a") == (
        state_root / "runners" / "lane-a" / "agent" / "logs"
    )
    assert store.resume_file(runner_id="lane-a") == (
        state_root / "runners" / "lane-a" / "agent" / "resume.state"
    )
    assert store.rotation_handoff_file(runner_id="lane-a") == (
        state_root / "runners" / "lane-a" / "agent" / "rotation-handoff.md"
    )
    assert store.next_task_file() == state_root / "auto-focus-next-task.txt"
