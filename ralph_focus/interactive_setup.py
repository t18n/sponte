"""Simple interactive entry-flow helpers for Ralph."""

from __future__ import annotations

from dataclasses import dataclass

from config.defaults import DEFAULT_EXECUTE_MODEL, DEFAULT_PLAN_MODEL


@dataclass(frozen=True)
class InteractiveChoice:
    id: str
    label: str


def resolve_choice_index(*, choice_count: int, raw_index: int) -> int:
    if raw_index < 1 or raw_index > choice_count:
        raise ValueError(f"choice index {raw_index} out of range 1..{choice_count}")
    return raw_index - 1


def auto_focus_entry_choices() -> list[InteractiveChoice]:
    return [
        InteractiveChoice("resume", "Resume an interrupted run"),
        InteractiveChoice(
            "complete-worktree",
            "Complete one cycle for a saved worktree (orphan recovery)",
        ),
        InteractiveChoice("specific-task", "Run a specific task path"),
        InteractiveChoice("task-list", "Pick from the current task list"),
    ]


def _inject_workspace(args: list[str], workspace: str | None) -> list[str]:
    if not workspace or not args:
        return args
    return [args[0], "--workspace", workspace, *args[1:]]


def build_exec_args(
    *,
    mode: str = "auto-focus",
    entry: str | None = None,
    value: str | None = None,
    workspace: str | None = None,
) -> list[str]:
    if mode != "auto-focus":
        raise ValueError(f"unknown mode: {mode}; only auto-focus is supported")

    args = ["auto-focus"]
    if entry == "resume":
        if not value:
            raise ValueError("resume requires a generation id")
        args.extend(["--resume", value])
    elif entry == "complete-worktree":
        if not value:
            raise ValueError("complete-worktree requires a worktree path")
        args.extend(["--complete-worktree", value])
    elif entry in ("specific-task", "task-list"):
        if not value:
            raise ValueError(f"{entry} requires a task value")
        args.append(value)

    args.extend(["--plan-model", DEFAULT_PLAN_MODEL, "--execute-model", DEFAULT_EXECUTE_MODEL])
    return _inject_workspace(args, workspace)
