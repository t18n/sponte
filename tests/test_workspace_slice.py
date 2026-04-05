"""Workspace registry, settings, init, and trunk resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from config.defaults import TASKS_DIR


def _git_init_with_commit(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "sponte-tests@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Sponte Tests"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "README.md").write_text("# t\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _git_create_linked_worktree(root: Path, name: str = "linked") -> Path:
    linked = root.parent / f"{root.name}-{name}"
    subprocess.run(["git", "branch", name], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "worktree", "add", str(linked), name], cwd=root, check=True, capture_output=True)
    return linked


def test_workspace_settings_roundtrip(tmp_path: Path) -> None:
    from ralph_focus.workspace_settings import (
        WorkspaceSettings,
        load_workspace_settings,
        save_workspace_settings,
        workspace_settings_path,
    )

    root = tmp_path / "repo"
    root.mkdir()
    assert load_workspace_settings(root).trunk_branch == "sponte"
    save_workspace_settings(root, WorkspaceSettings(trunk_branch="develop"))
    assert workspace_settings_path(root).is_file()
    loaded = load_workspace_settings(root)
    assert loaded.trunk_branch == "develop"


def test_known_workspaces_registry_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    from ralph_focus.workspaces_registry import load_known_workspaces, register_workspace, save_known_workspaces

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    save_known_workspaces([b, a])
    register_workspace(a)
    reg = load_known_workspaces()
    assert reg[0] == a.resolve()
    assert b.resolve() in reg


def test_resolve_git_repo_root_uses_primary_checkout_for_linked_worktree_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rich.console import Console

    from ralph_focus.workspace_resolve import resolve_git_repo_root

    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    linked = _git_create_linked_worktree(root)

    resolved = resolve_git_repo_root(linked, console=Console(stderr=True), interactive=False)

    assert resolved == root.resolve()


def test_resolve_git_repo_root_uses_primary_checkout_from_linked_worktree_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rich.console import Console

    from ralph_focus.workspace_resolve import resolve_git_repo_root

    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    linked = _git_create_linked_worktree(root, "linked-cwd")
    monkeypatch.chdir(linked)

    resolved = resolve_git_repo_root(None, console=Console(stderr=True), interactive=False)

    assert resolved == root.resolve()


def test_init_sponte_adds_gitignore_and_tasks(tmp_path: Path) -> None:
    from ralph_focus.workspace_init import init_sponte_workspace
    from ralph_focus.workspace_tasks import sponte_tasks_layout_valid

    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    src = tmp_path / "seed.md"
    src.write_text("task: Seed\n\n- [ ] one\n", encoding="utf-8")

    init_sponte_workspace(root, source=src, trunk_branch="sponte")

    gi = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".sponte/worktrees/" in gi
    assert ".sponte/\n" not in gi
    assert ".sponte\n" not in gi
    assert sponte_tasks_layout_valid(root)
    assert (root / TASKS_DIR / "backlog" / "seed.md").is_file()


def test_resolve_trunk_branch_creates_configured_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    from ralph_focus.workspace_resolve import resolve_trunk_branch_ref

    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)

    name = resolve_trunk_branch_ref(root, cli_override=None)
    assert name == "sponte"
    proc = subprocess.run(
        ["git", "branch", "--list", "sponte"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "sponte" in proc.stdout


def test_resolve_trunk_branch_cli_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    from ralph_focus.workspace_resolve import resolve_trunk_branch_ref

    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)

    assert resolve_trunk_branch_ref(root, cli_override="topic") == "topic"
    proc = subprocess.run(
        ["git", "branch", "--list", "topic"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "topic" in proc.stdout


def test_plan_cli_initializes_workspace_without_running_cycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ralph_focus import cli
    from ralph_focus import workspace_resolve

    seen: dict[str, object] = {"run_one_cycle": 0}
    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    src = tmp_path / "seed.md"
    src.write_text("task: Seed\n\n- [ ] one\n", encoding="utf-8")

    monkeypatch.setattr(cli, "_cli_allows_prompts", lambda: True)
    monkeypatch.setattr(
        workspace_resolve.Prompt,
        "ask",
        lambda *args, **kwargs: str(src) if "Source path" in args[0] else "sponte",
    )
    monkeypatch.setattr(cli, "run_one_cycle", lambda *_args, **_kwargs: seen.__setitem__("run_one_cycle", 1) or 0)
    monkeypatch.setattr(cli, "run_preflight", lambda **_k: (_ for _ in ()).throw(AssertionError("plan should not preflight")))
    monkeypatch.setattr(cli, "get_harness", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("plan should not get harness")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["plan", "--workspace", str(root)])

    assert result.exit_code == 0
    assert seen["run_one_cycle"] == 0
    assert (root / TASKS_DIR / "backlog" / "seed.md").is_file()


def test_plan_cli_persists_trunk_override_for_initialized_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ralph_focus import cli
    from ralph_focus.workspace_init import init_sponte_workspace
    from ralph_focus.workspace_settings import load_workspace_settings

    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    src = tmp_path / "seed.md"
    src.write_text("task: Seed\n\n- [ ] one\n", encoding="utf-8")
    init_sponte_workspace(root, source=src, trunk_branch="sponte")

    monkeypatch.setattr(cli, "_cli_allows_prompts", lambda: False)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["plan", "--workspace", str(root), "--trunk-branch", "develop"])

    assert result.exit_code == 0
    assert load_workspace_settings(root).trunk_branch == "develop"
    proc = subprocess.run(
        ["git", "branch", "--list", "develop"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "develop" in proc.stdout


def test_plan_cli_rejected_trunk_override_does_not_modify_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ralph_focus import cli
    from ralph_focus.workspace_init import init_sponte_workspace
    from ralph_focus.workspace_settings import load_workspace_settings

    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    src = tmp_path / "seed.md"
    src.write_text("task: Seed\n\n- [ ] one\n", encoding="utf-8")
    init_sponte_workspace(root, source=src, trunk_branch="sponte")

    monkeypatch.setattr(cli, "_cli_allows_prompts", lambda: False)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["plan", "--workspace", str(root), "--trunk-branch", "bad name"])

    assert result.exit_code != 0
    assert load_workspace_settings(root).trunk_branch == "sponte"


def test_auto_focus_stops_after_interactive_init(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    seen: dict[str, int] = {"run_one_cycle": 0}

    monkeypatch.setattr(cli, "_cli_allows_prompts", lambda: True)
    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *_args, **_kwargs: root)
    monkeypatch.setattr(cli, "ensure_tasks_layout_with_prompt", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cli, "run_preflight", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should stop before preflight")))
    monkeypatch.setattr(
        cli,
        "run_one_cycle",
        lambda *_args, **_kwargs: seen.__setitem__("run_one_cycle", seen["run_one_cycle"] + 1) or 0,
    )

    runner = CliRunner()
    result = runner.invoke(cli.app, ["auto-focus", "--workspace", str(root)])

    assert result.exit_code == 0
    assert seen["run_one_cycle"] == 0
    output = (result.stdout + result.stderr).lower()
    assert "review" in output
    assert "rerun" in output


def test_build_exec_args_inserts_workspace_for_worktree_commands() -> None:
    from ralph_focus.interactive_setup import build_exec_args

    assert build_exec_args(mode="worktree-remove", workspace="/tmp/w") == [
        "worktree-remove",
        "--workspace",
        "/tmp/w",
    ]
