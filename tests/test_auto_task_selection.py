"""Tests for plan-model backlog selection (no priorities.md ordering)."""

from pathlib import Path

import pytest

from config.defaults import TASKS_DIR
from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities, RunRequest, RunResult


def _git_init(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("# t\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


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


def test_select_next_task_abs_uses_plan_model_not_priorities(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Backlog pick runs with plan_model; missing priorities.md does not block selection."""
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "state"))
    from ralph_focus import cycle
    from ralph_focus.paths import next_task_file
    from ralph_focus.task_jobs import TaskJobStatus, write_task_job_status
    from ralph_focus.workspace_settings import WorkspaceSettings, save_workspace_settings

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    backlog = repo / TASKS_DIR / "backlog"
    backlog.mkdir(parents=True, exist_ok=True)
    (backlog / "alpha.md").write_text("task: Alpha\n\n- [ ] a\n", encoding="utf-8")
    (backlog / "beta.md").write_text("task: Beta\n\n- [ ] b\n", encoding="utf-8")

    pri = repo / TASKS_DIR / "priorities.md"
    assert not pri.is_file()

    custom = repo / ".sponte" / "prompts" / "my_agent_pick.md"
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_text(
        "Custom picker.\n__CLAIMED_TASKS__\n__BACKLOG_CANDIDATES__\n"
        "Write one line to __NEXT_TASK_FILE__\n",
        encoding="utf-8",
    )
    save_workspace_settings(repo, WorkspaceSettings(prompts={"agent_pick_task": ".sponte/prompts/my_agent_pick.md"}))

    write_task_job_status(
        repo,
        TaskJobStatus(
            task_id="claimed-1",
            rel_task=f"{TASKS_DIR}/in-progress/other.md",
            stage="in-progress",
            owning_session_id="rap-other",
            task_title="Other",
        ),
    )

    cfg = cycle.AutoFocusConfig(
        primary=repo,
        harness=_Harness(),
        plan_model="plan-model-x",
        execute_model="execute-model-y",
        allow_agent_pick=True,
        task_arg="",
    )

    models_seen: list[str] = []

    def fake_run_agent(cwd: Path, model: str, body: str, logf: Path, label: str) -> int:
        models_seen.append(model)
        assert "Custom picker." in body
        assert "rap-other" in body
        assert f"{TASKS_DIR}/backlog/beta.md" in body
        nf = next_task_file(repo)
        nf.parent.mkdir(parents=True, exist_ok=True)
        nf.write_text(f"{TASKS_DIR}/backlog/beta.md\n", encoding="utf-8")
        return 0

    table_calls: list[object] = []

    def _no_table(c: cycle.AutoFocusConfig) -> None:
        table_calls.append(c)

    monkeypatch.setattr(cfg, "_run_agent", fake_run_agent)
    monkeypatch.setattr(cycle, "_append_phase_log", lambda *_a, **_k: None)
    monkeypatch.setattr(cycle, "_print_selectable_tasks_table", _no_table)

    code, picked = cycle._select_next_task_abs(cfg)

    assert code == 0
    assert picked == repo / TASKS_DIR / "backlog" / "beta.md"
    assert models_seen == ["plan-model-x"]
    assert table_calls == []


def test_select_next_task_abs_no_agent_pick_returns_no_actionable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "state"))
    from ralph_focus import cycle

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / TASKS_DIR / "backlog").mkdir(parents=True, exist_ok=True)
    (repo / TASKS_DIR / "backlog" / "t.md").write_text("task: T\n\n- [ ] x\n", encoding="utf-8")

    cfg = cycle.AutoFocusConfig(
        primary=repo,
        harness=_Harness(),
        plan_model="p",
        execute_model="e",
        allow_agent_pick=False,
        task_arg="",
    )

    code, picked = cycle._select_next_task_abs(cfg)

    assert code == 2
    assert picked is None
