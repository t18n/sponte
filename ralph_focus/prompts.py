"""Load bundled prompt templates and render current path placeholders."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ralph_focus.paths import guardrails_markdown_path, next_task_file, progress_markdown_path, sponte_job_task_dir
from ralph_focus.tasks import task_root


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


def resolve_prompt_template_path(name: str, primary: Path) -> Path:
    """
    Bundled ``prompts/<name>.md`` unless ``.sponte/settings.json`` maps ``prompts.<name>``
    to a repo-relative markdown file (must stay under *primary*).
    """
    from ralph_focus.workspace_settings import load_workspace_settings

    rel = load_workspace_settings(primary).prompts.get(name, "").strip()
    if rel:
        candidate = (primary / rel).resolve()
        try:
            candidate.relative_to(primary.resolve())
        except ValueError:
            return prompt_path(name)
        if candidate.is_file():
            return candidate
    return prompt_path(name)


def load_prompt_for_workspace(name: str, primary: Path) -> str:
    return resolve_prompt_template_path(name, primary).read_text(encoding="utf-8")


def render_prompt(
    name: str,
    *,
    primary: Path,
    task_rel: str,
    plan_rel: str,
    verify_commands: str = "",
    claimed_tasks_snapshot: str = "",
    backlog_candidates: str = "",
    task_body_excerpt: str = "",
    naming_reply_path: str = "",
    task_id: str = "",
) -> str:
    return substitute(
        load_prompt_for_workspace(name, primary),
        primary=primary,
        task_rel=task_rel,
        plan_rel=plan_rel,
        verify_commands=verify_commands,
        claimed_tasks_snapshot=claimed_tasks_snapshot,
        backlog_candidates=backlog_candidates,
        task_body_excerpt=task_body_excerpt,
        naming_reply_path=naming_reply_path,
        task_id=task_id,
    )


def substitute(
    template: str,
    *,
    primary: Path,
    task_rel: str,
    plan_rel: str,
    verify_commands: str = "",
    claimed_tasks_snapshot: str = "",
    backlog_candidates: str = "",
    task_body_excerpt: str = "",
    naming_reply_path: str = "",
    task_id: str = "",
) -> str:
    task_status_file = ""
    if task_id.strip():
        task_status_file = (sponte_job_task_dir(primary, task_id) / "status.json").as_posix()
    return (
        template.replace("__TASK_FILE__", task_rel)
        .replace("__PLAN_FILE__", plan_rel)
        .replace("__TASKS_ROOT__", task_root(primary))
        .replace("__GUARDRAILS_FILE__", guardrails_markdown_path(primary).relative_to(primary).as_posix())
        .replace("__PROGRESS_FILE__", progress_markdown_path(primary).relative_to(primary).as_posix())
        .replace("__NEXT_TASK_FILE__", next_task_file(primary).as_posix())
        .replace("__VERIFY_COMMANDS__", verify_commands)
        .replace("__CLAIMED_TASKS__", claimed_tasks_snapshot)
        .replace("__BACKLOG_CANDIDATES__", backlog_candidates)
        .replace("__TASK_BODY_EXCERPT__", task_body_excerpt)
        .replace("__NAMING_REPLY_PATH__", naming_reply_path)
        .replace("__TASK_STATUS_FILE__", task_status_file)
    )
