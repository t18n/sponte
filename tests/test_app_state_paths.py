"""Tests for Sponte app-state vs workspace `.sponte/` path boundary."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_workspace_runtime_root_uses_sponte_state_dir_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "state-root"))
    from ralph_focus.app_state_paths import workspace_runtime_root

    ws = tmp_path / "my-repo"
    root = workspace_runtime_root(ws)
    assert root.parent.parent == tmp_path / "state-root"
    assert root.parent.name == "workspaces"
    assert len(root.name) == 32


def test_workspace_runtime_root_is_stable_per_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    from ralph_focus.app_state_paths import workspace_runtime_root

    ws = tmp_path / "repo"
    assert workspace_runtime_root(ws) == workspace_runtime_root(ws)


def test_workspace_runtime_root_differs_for_different_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    from ralph_focus.app_state_paths import workspace_runtime_root

    a = tmp_path / "a"
    b = tmp_path / "b"
    assert workspace_runtime_root(a) != workspace_runtime_root(b)


def test_ralph_data_dir_matches_workspace_runtime_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    from ralph_focus.app_state_paths import workspace_runtime_root
    from ralph_focus.paths import ralph_data_dir

    ws = tmp_path / "repo"
    assert ralph_data_dir(ws) == workspace_runtime_root(ws)


def test_guardrails_path_under_workspace_sponte(tmp_path: Path) -> None:
    from config.defaults import GUARDRAILS_BASENAME, SPONTE_DIR
    from ralph_focus.paths import guardrails_markdown_path

    assert guardrails_markdown_path(tmp_path) == tmp_path / SPONTE_DIR / GUARDRAILS_BASENAME


def test_worktrees_base_matches_worktree_base_dir_default(tmp_path: Path) -> None:
    from config.defaults import WORKTREE_BASE_DIR
    from ralph_focus.paths import worktrees_base

    assert worktrees_base(tmp_path) == tmp_path / WORKTREE_BASE_DIR


def test_worktrees_base_uses_workspace_setting_override(tmp_path: Path) -> None:
    from ralph_focus.paths import worktrees_base
    from ralph_focus.workspace_settings import WorkspaceSettings, save_workspace_settings

    save_workspace_settings(tmp_path, WorkspaceSettings(worktree_root=".sponte/custom-worktrees"))

    assert worktrees_base(tmp_path) == tmp_path / ".sponte/custom-worktrees"


def test_sponte_state_base_dir_uses_xdg_when_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPONTE_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    from ralph_focus.app_state_paths import sponte_state_base_dir

    assert sponte_state_base_dir() == (tmp_path / "xdg" / "sponte").resolve()


def test_sponte_state_base_dir_uses_macos_library_on_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPONTE_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    from ralph_focus import app_state_paths

    monkeypatch.setattr(app_state_paths.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(app_state_paths.Path, "home", classmethod(lambda cls: Path("/Users/demo")))

    assert app_state_paths.sponte_state_base_dir() == Path("/Users/demo/Library/Application Support/sponte")


def test_readable_base_files_fall_back_to_legacy_repo_paths(tmp_path: Path) -> None:
    from config.defaults import LEGACY_RALPH_DATA_DIR
    from ralph_focus.paths import readable_base_sha_file, readable_base_task_file

    legacy_dir = tmp_path / LEGACY_RALPH_DATA_DIR
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_sha = legacy_dir / "auto-focus-base-sha"
    legacy_task = legacy_dir / "auto-focus-base-task"
    legacy_sha.write_text("abc123\n", encoding="utf-8")
    legacy_task.write_text(".agents/tasks/backlog/demo.md\n", encoding="utf-8")

    assert readable_base_sha_file(tmp_path) == legacy_sha
    assert readable_base_task_file(tmp_path) == legacy_task
