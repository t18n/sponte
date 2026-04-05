"""Load prompt templates from `.agents/ralph/prompts/*.md`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


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


def substitute(
    template: str,
    *,
    task_rel: str,
    plan_rel: str,
    verify_commands: str = "",
) -> str:
    return (
        template.replace("__TASK_FILE__", task_rel)
        .replace("__PLAN_FILE__", plan_rel)
        .replace("__VERIFY_COMMANDS__", verify_commands)
    )
