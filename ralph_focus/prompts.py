"""Load bundled prompt templates and render current path placeholders."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ralph_focus.paths import guardrails_markdown_path, next_task_file, progress_markdown_path
from ralph_focus.tasks import priorities_file, task_root


def _ralph_root() -> Path:
    return Path(__file__).resolve().parent.parent


@lru_cache
def prompts_dir() -> Path:
    return _ralph_root() / "prompts"


def prompt_path(name: str) -> Path:
    return prompts_dir() / f"{name}.md"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    p = prompt_path(name)
    return p.read_text(encoding="utf-8")


def render_prompt(
    name: str,
    *,
    primary: Path,
    task_rel: str,
    plan_rel: str,
    verify_commands: str = "",
) -> str:
    return substitute(
        load_prompt(name),
        primary=primary,
        task_rel=task_rel,
        plan_rel=plan_rel,
        verify_commands=verify_commands,
    )


def substitute(
    template: str,
    *,
    primary: Path,
    task_rel: str,
    plan_rel: str,
    verify_commands: str = "",
) -> str:
    return (
        template.replace("__TASK_FILE__", task_rel)
        .replace("__PLAN_FILE__", plan_rel)
        .replace("__TASKS_ROOT__", task_root(primary))
        .replace("__PRIORITIES_FILE__", priorities_file(primary).relative_to(primary).as_posix())
        .replace("__GUARDRAILS_FILE__", guardrails_markdown_path(primary).relative_to(primary).as_posix())
        .replace("__PROGRESS_FILE__", progress_markdown_path(primary).relative_to(primary).as_posix())
        .replace("__NEXT_TASK_FILE__", next_task_file(primary).as_posix())
        .replace("__VERIFY_COMMANDS__", verify_commands)
    )
