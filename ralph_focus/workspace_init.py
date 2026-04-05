"""Initialize ``.sponte`` in a git workspace (tasks layout, gitignore, settings)."""

from __future__ import annotations

import shutil
from pathlib import Path

from config.defaults import SPONTE_DIR, TASKS_DIR, WORKTREE_BASE_DIR
from ralph_focus.git_ops import trunk_branch_ref
from ralph_focus.workspace_settings import (
    WorkspaceSettings,
    load_workspace_settings,
    save_workspace_settings,
    workspace_settings_path,
)
from ralph_focus.tasks import task_has_pending
from ralph_focus.workspace_tasks import sponte_tasks_layout_valid


GITIGNORE_ENTRY = f"{WORKTREE_BASE_DIR}/\n"


def _gitignore_covers_sponte(text: str) -> bool:
    for line in text.splitlines():
        s = line.strip()
        if s == WORKTREE_BASE_DIR or s == f"{WORKTREE_BASE_DIR}/":
            return True
    return False


def ensure_gitignore_sponte(repo_root: Path) -> None:
    gi = repo_root / ".gitignore"
    if not gi.is_file():
        gi.write_text(GITIGNORE_ENTRY, encoding="utf-8")
        return
    text = gi.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    rewritten = False
    normalized_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in {".sponte", ".sponte/"}:
            normalized_lines.append(WORKTREE_BASE_DIR + "/")
            rewritten = True
            continue
        normalized_lines.append(line)
    normalized_text = "\n".join(normalized_lines)
    if lines:
        normalized_text += "\n"
    if rewritten:
        gi.write_text(normalized_text, encoding="utf-8")
        text = normalized_text
    if _gitignore_covers_sponte(text):
        return
    with gi.open("a", encoding="utf-8") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(GITIGNORE_ENTRY)


def _write_priorities_from_backlog(repo: Path) -> None:
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
    for stage in ("backlog", "in-progress", "completed"):
        (repo_root / TASKS_DIR / stage).mkdir(parents=True, exist_ok=True)
    ensure_gitignore_sponte(repo_root)
    settings = load_workspace_settings(repo_root)
    settings_exists = workspace_settings_path(repo_root).is_file()
    if trunk_branch is not None and trunk_branch.strip():
        validated = trunk_branch_ref(repo_root, trunk_name=trunk_branch.strip())
        settings = WorkspaceSettings(trunk_branch=validated)
        save_workspace_settings(repo_root, settings)
    elif not settings_exists:
        validated = trunk_branch_ref(repo_root, trunk_name=settings.normalized_trunk())
        save_workspace_settings(repo_root, WorkspaceSettings(trunk_branch=validated))

    if source is not None:
        import_tasks_from_source(source, repo_root)
    if not (repo_root / TASKS_DIR / "priorities.md").is_file():
        _write_priorities_from_backlog(repo_root)
    if not sponte_tasks_layout_valid(repo_root):
        raise RuntimeError("initialization did not produce a valid tasks layout")


__all__ = [
    "ensure_gitignore_sponte",
    "import_tasks_from_source",
    "init_sponte_workspace",
]
