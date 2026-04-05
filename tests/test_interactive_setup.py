import sys
from pathlib import Path

import pytest

from config.defaults import TASKS_DIR
from ralph_focus.interactive_setup import (
    auto_focus_entry_choices,
    build_exec_args,
    mode_choices,
    resolve_choice_index,
)


def test_mode_choices_include_existing_entry_points() -> None:
    ids = [choice.id for choice in mode_choices()]
    assert "auto-focus" in ids
    assert "smoke" in ids
    assert "worktree-remove" in ids


def test_auto_focus_entry_includes_complete_worktree() -> None:
    ids = [choice.id for choice in auto_focus_entry_choices()]
    assert "complete-worktree" in ids


def test_resume_flow_builds_auto_focus_resume_command() -> None:
    args = build_exec_args(mode="auto-focus", entry="resume", value="lane-a")
    assert args[:2] == ["auto-focus", "--resume"]
    assert args[2] == "lane-a"


def test_complete_worktree_flow_builds_flag_and_path() -> None:
    args = build_exec_args(
        mode="auto-focus",
        entry="complete-worktree",
        value="/abs/path/to/worktree",
    )
    assert args[:3] == ["auto-focus", "--complete-worktree", "/abs/path/to/worktree"]


def test_complete_worktree_requires_path() -> None:
    with pytest.raises(ValueError):
        build_exec_args(mode="auto-focus", entry="complete-worktree", value="")
    with pytest.raises(ValueError):
        build_exec_args(mode="auto-focus", entry="complete-worktree", value=None)


def test_resume_flow_requires_generation_id() -> None:
    with pytest.raises(ValueError):
        build_exec_args(mode="auto-focus", entry="resume", value="")


def test_resume_flow_requires_generation_id_when_missing() -> None:
    with pytest.raises(ValueError):
        build_exec_args(mode="auto-focus", entry="resume", value=None)


def test_task_list_flow_builds_explicit_task_command() -> None:
    args = build_exec_args(
        mode="auto-focus",
        entry="task-list",
        value=f"{TASKS_DIR}/backlog/example.md",
    )
    assert args[0] == "auto-focus"
    assert args[1] == f"{TASKS_DIR}/backlog/example.md"


def test_task_list_flow_requires_selected_task() -> None:
    with pytest.raises(ValueError):
        build_exec_args(mode="auto-focus", entry="task-list", value=None)


def test_invalid_choice_index_is_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_choice_index(choice_count=3, raw_index=0)
    with pytest.raises(ValueError):
        resolve_choice_index(choice_count=3, raw_index=4)


def test_interactive_cli_reexecs_via_local_checkout(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    picks = iter(["auto-focus", "resume"])
    monkeypatch.setattr(cli, "_pick_interactive_choice", lambda *_args, **_kwargs: next(picks))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *_args, **_kwargs: "lane-a")

    observed: dict[str, object] = {}

    def fake_execv(file: str, args: list[str]) -> None:
        observed["file"] = file
        observed["args"] = args
        raise SystemExit(0)

    monkeypatch.setattr(cli.os, "execv", fake_execv)

    with pytest.raises(SystemExit):
        cli.cmd_interactive()

    assert observed == {
        "file": sys.executable,
        "args": [
            sys.executable,
            "-m",
            "ralph_focus.cli",
            "auto-focus",
            "--workspace",
            str(tmp_path),
            "--resume",
            "lane-a",
            "--plan-model",
            "auto",
            "--execute-model",
            "auto",
        ],
    }


def test_interactive_complete_worktree_uses_git_root_without_task_validation(
    monkeypatch, tmp_path: Path
) -> None:
    from ralph_focus import cli

    monkeypatch.setattr(cli, "resolve_git_repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        cli,
        "resolve_primary_workspace",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("task validation should not run")),
    )
    monkeypatch.setattr(cli, "list_recoverable_resumes", lambda _primary: [])
    picks = iter(["auto-focus", "complete-worktree"])
    monkeypatch.setattr(cli, "_pick_interactive_choice", lambda *_args, **_kwargs: next(picks))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *_args, **_kwargs: str(tmp_path / "wt"))

    observed: dict[str, object] = {}

    def fake_execv(file: str, args: list[str]) -> None:
        observed["file"] = file
        observed["args"] = args
        raise SystemExit(0)

    monkeypatch.setattr(cli.os, "execv", fake_execv)

    with pytest.raises(SystemExit):
        cli.cmd_interactive()

    assert observed == {
        "file": sys.executable,
        "args": [
            sys.executable,
            "-m",
            "ralph_focus.cli",
            "auto-focus",
            "--workspace",
            str(tmp_path),
            "--complete-worktree",
            str((tmp_path / "wt").resolve()),
            "--plan-model",
            "auto",
            "--execute-model",
            "auto",
        ],
    }
