"""Tests for workspace_command_detection."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_detect_rust(tmp_path: Path) -> None:
    from ralph_focus.workspace_command_detection import detect_workspace_commands

    root = tmp_path / "rust"
    root.mkdir()
    (root / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")

    c = detect_workspace_commands(root)
    assert c.check == "cargo check"
    assert c.test == "cargo test"
    assert c.verify[0] == "cargo check"


def test_detect_go(tmp_path: Path) -> None:
    from ralph_focus.workspace_command_detection import detect_workspace_commands

    root = tmp_path / "go"
    root.mkdir()
    (root / "go.mod").write_text("module example.com/x\ngo 1.22\n", encoding="utf-8")

    c = detect_workspace_commands(root)
    assert "go test" in c.test
    assert c.verify


def test_detect_python_pytest_via_pyproject(tmp_path: Path) -> None:
    from ralph_focus.workspace_command_detection import detect_workspace_commands

    root = tmp_path / "py"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\nname = \"x\"\nversion = \"0\"\n[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )

    c = detect_workspace_commands(root)
    assert c.test == "python -m pytest -q"
    assert c.verify == ("python -m pytest -q",)


def test_detect_python_uv_lock(tmp_path: Path) -> None:
    from ralph_focus.workspace_command_detection import detect_workspace_commands

    root = tmp_path / "py"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\ndependencies = [\"pytest\"]\n",
        encoding="utf-8",
    )
    (root / "uv.lock").write_text("# lock\n", encoding="utf-8")

    c = detect_workspace_commands(root)
    assert c.install == "uv sync"
    assert c.test == "uv run pytest -q"


def test_mixed_stack_skips_auto_detection(tmp_path: Path) -> None:
    from ralph_focus.workspace_command_detection import detect_workspace_commands
    from ralph_focus.workspace_settings import WorkspaceCommandSettings

    root = tmp_path / "mixed"
    root.mkdir()
    (root / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
    (root / "package.json").write_text('{"name":"x"}', encoding="utf-8")

    c = detect_workspace_commands(root)
    assert c == WorkspaceCommandSettings()


def test_resolved_default_test_command_matches_detection(tmp_path: Path) -> None:
    from ralph_focus.workspace_command_detection import (
        DEFAULT_FALLBACK_TEST_COMMAND,
        resolved_default_test_command,
    )
    from ralph_focus.workspace_init import init_sponte_workspace

    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\nname = \"x\"\nversion = \"0\"\n[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )
    assert resolved_default_test_command(root) == "python -m pytest -q"

    empty = tmp_path / "empty"
    empty.mkdir()
    assert resolved_default_test_command(empty) == DEFAULT_FALLBACK_TEST_COMMAND

    gitroot = tmp_path / "gitpy"
    gitroot.mkdir()
    # init_sponte_workspace needs git for trunk_branch_ref - skip full init; save settings with test
    from ralph_focus.workspace_settings import WorkspaceCommandSettings, WorkspaceSettings, save_workspace_settings

    save_workspace_settings(
        gitroot,
        WorkspaceSettings(commands=WorkspaceCommandSettings(test="custom test cmd")),
    )
    assert resolved_default_test_command(gitroot) == "custom test cmd"


def test_detect_python_verify_includes_build_when_packaging(tmp_path: Path) -> None:
    from ralph_focus.workspace_command_detection import detect_workspace_commands

    root = tmp_path / "py"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[build-system]\nrequires = [\"setuptools\"]\nbuild-backend = \"setuptools.build_meta\"\n"
        "[project]\nname = \"x\"\nversion = \"0\"\n[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )

    c = detect_workspace_commands(root)
    assert c.build == "python -m build"
    assert c.test == "python -m pytest -q"
    assert c.verify == ("python -m build", "python -m pytest -q")
