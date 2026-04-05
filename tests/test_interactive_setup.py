import sys
from pathlib import Path

import pytest

from ralph_focus.interactive_setup import (
    build_exec_args,
    mode_choices,
    resolve_choice_index,
)


def test_mode_choices_include_existing_entry_points() -> None:
    ids = [choice.id for choice in mode_choices()]
    assert "auto-focus" in ids
    assert "smoke" in ids
    assert "worktree-remove" in ids


def test_resume_flow_builds_auto_focus_resume_command() -> None:
    args = build_exec_args(mode="auto-focus", entry="resume", value="lane-a")
    assert args[:2] == ["auto-focus", "--resume"]
    assert args[2] == "lane-a"


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
        value=".agents/tasks/backlog/example.md",
    )
    assert args[0] == "auto-focus"
    assert args[1] == ".agents/tasks/backlog/example.md"


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

    monkeypatch.setattr(cli, "_ensure_repo", lambda: tmp_path)
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
            str(tmp_path),
            "auto-focus",
            "--resume",
            "lane-a",
            "--plan-model",
            "auto",
            "--execute-model",
            "auto",
        ],
    }
