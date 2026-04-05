"""Initialize ``.sponte`` in a git workspace (tasks layout, gitignore, settings)."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from config.defaults import SPONTE_DIR, TASKS_DIR, WORKTREE_BASE_DIR
from ralph_focus.git_ops import trunk_branch_ref
from ralph_focus.paths import worktrees_base
from ralph_focus.workspace_command_detection import detect_workspace_commands
from ralph_focus.workspace_settings import (
    WorkspaceSettings,
    load_workspace_settings,
    merge_command_settings,
    save_workspace_settings,
    workspace_settings_path,
)
from ralph_focus.tasks import task_has_pending
from ralph_focus.workspace_tasks import sponte_tasks_layout_valid


def _gitignore_entry(worktree_root: str) -> str:
    return f"{worktree_root.rstrip('/')}/\n"


def _gitignore_covers_sponte(text: str) -> bool:
    return _gitignore_covers_path(text, WORKTREE_BASE_DIR)


def _gitignore_covers_path(text: str, rel_path: str) -> bool:
    for line in text.splitlines():
        s = line.strip()
        if s == rel_path or s == f"{rel_path}/":
            return True
    return False


def ensure_gitignore_sponte(repo_root: Path, worktree_root: str = WORKTREE_BASE_DIR) -> None:
    gi = repo_root / ".gitignore"
    normalized_worktree_root = worktree_root.rstrip("/")
    entry = _gitignore_entry(normalized_worktree_root)
    if not gi.is_file():
        gi.write_text(entry, encoding="utf-8")
        return
    text = gi.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    rewritten = False
    normalized_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in {".sponte", ".sponte/"}:
            normalized_lines.append(normalized_worktree_root + "/")
            rewritten = True
            continue
        normalized_lines.append(line)
    normalized_text = "\n".join(normalized_lines)
    if lines:
        normalized_text += "\n"
    if rewritten:
        gi.write_text(normalized_text, encoding="utf-8")
        text = normalized_text
    if _gitignore_covers_path(text, normalized_worktree_root):
        return
    with gi.open("a", encoding="utf-8") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(entry)


def refresh_priorities_from_backlog(repo: Path) -> None:
    backlog = repo / TASKS_DIR / "backlog"
    md_files = sorted({p.resolve() for p in backlog.rglob("*.md")})
    lines = ["# Priorities", ""]
    tasks_root = repo / TASKS_DIR
    for p in md_files:
        try:
            rel = p.relative_to(tasks_root).as_posix()
        except ValueError:
            continue
        label = p.stem.replace("-", " ")
        lines.append(f"- [{label}](./{rel})")
    lines.append("")
    pri = tasks_root / "priorities.md"
    pri.write_text("\n".join(lines), encoding="utf-8")


def _ensure_markdown_has_pending_item(path: Path) -> None:
    if not path.is_file() or task_has_pending(path):
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n## Sponte\n\n- [ ] Complete this task\n"
    path.write_text(text, encoding="utf-8")


def import_tasks_from_source(source: Path, repo: Path) -> None:
    """Copy markdown tasks from a file or directory into ``.sponte/tasks/backlog``."""
    dest_root = repo / TASKS_DIR
    backlog = dest_root / "backlog"
    backlog.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        shutil.copy2(source, backlog / source.name)
        _ensure_markdown_has_pending_item(backlog / source.name)
        return
    if source.is_dir():
        for p in sorted(source.rglob("*.md")):
            rel = p.relative_to(source)
            dest = backlog / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
            _ensure_markdown_has_pending_item(dest)
        return
    raise FileNotFoundError(f"source not found: {source}")


def init_sponte_workspace(
    repo_root: Path,
    *,
    source: Path | None,
    trunk_branch: str | None = None,
) -> None:
    """Create ``.sponte`` tree, ensure gitignore, optional task import, default settings."""
    sponte = repo_root / SPONTE_DIR
    sponte.mkdir(parents=True, exist_ok=True)
    for stage in ("backlog", "in-progress", "review-required", "completed"):
        (repo_root / TASKS_DIR / stage).mkdir(parents=True, exist_ok=True)
    settings = load_workspace_settings(repo_root)
    settings_exists = workspace_settings_path(repo_root).is_file()
    if trunk_branch is not None and trunk_branch.strip():
        validated = trunk_branch_ref(repo_root, trunk_name=trunk_branch.strip())
        settings = replace(settings, trunk_branch=validated)
    elif not settings_exists:
        validated = trunk_branch_ref(repo_root, trunk_name=settings.normalized_trunk())
        settings = replace(settings, trunk_branch=validated)

    pre_merge_commands = settings.commands
    detected = detect_workspace_commands(repo_root)
    merged_commands = merge_command_settings(settings.commands, detected)
    settings = replace(settings, commands=merged_commands)
    commands_changed = merged_commands != pre_merge_commands

    ensure_gitignore_sponte(repo_root, settings.normalized_worktree_root())
    if not settings_exists or trunk_branch is not None or commands_changed:
        save_workspace_settings(repo_root, settings)
    worktrees_base(repo_root).mkdir(parents=True, exist_ok=True)

    if source is not None:
        import_tasks_from_source(source, repo_root)
    if not (repo_root / TASKS_DIR / "priorities.md").is_file():
        refresh_priorities_from_backlog(repo_root)
    if not sponte_tasks_layout_valid(repo_root):
        raise RuntimeError("initialization did not produce a valid tasks layout")


def refresh_workspace_commands(repo_root: Path) -> bool:
    """
    Merge detected commands into existing settings and save if anything changed.

    Used when a workspace is already initialized (e.g. re-run ``sponte init``) to
    backfill new ``commands.*`` fields without overwriting user-set values.
    """
    settings = load_workspace_settings(repo_root)
    merged = merge_command_settings(settings.commands, detect_workspace_commands(repo_root))
    if merged == settings.commands:
        return False
    save_workspace_settings(repo_root, replace(settings, commands=merged))
    return True


__all__ = [
    "ensure_gitignore_sponte",
    "import_tasks_from_source",
    "init_sponte_workspace",
    "refresh_priorities_from_backlog",
    "refresh_workspace_commands",
]
