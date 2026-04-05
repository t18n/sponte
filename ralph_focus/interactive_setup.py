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


def mode_choices() -> list[InteractiveChoice]:
    return [
        InteractiveChoice("auto-focus", "Auto-focus task cycle"),
        InteractiveChoice("smoke", "Run smoke checks"),
        InteractiveChoice("worktree-remove", "Remove a Ralph worktree"),
        InteractiveChoice("worktree-prune-clean", "Prune clean Ralph worktrees"),
    ]


def auto_focus_entry_choices() -> list[InteractiveChoice]:
    return [
        InteractiveChoice("resume", "Resume an interrupted run"),
        InteractiveChoice("specific-task", "Run a specific task path"),
        InteractiveChoice("task-list", "Pick from the current task list"),
    ]


def build_exec_args(*, mode: str, entry: str | None = None, value: str | None = None) -> list[str]:
    if mode == "smoke":
        return ["smoke"]
    if mode == "worktree-remove":
        return ["worktree-remove"]
    if mode == "worktree-prune-clean":
        return ["worktree-prune-clean"]
    if mode != "auto-focus":
        raise ValueError(f"unknown interactive mode: {mode}")

    args = ["auto-focus"]
    if entry == "resume":
        if not value:
            raise ValueError("resume requires a generation id")
        args.extend(["--resume", value])
    elif entry in ("specific-task", "task-list"):
        if not value:
            raise ValueError(f"{entry} requires a task value")
        args.append(value)

    args.extend(["--plan-model", DEFAULT_PLAN_MODEL, "--execute-model", DEFAULT_EXECUTE_MODEL])
    return args
