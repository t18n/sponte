"""Prune/remove Ralph-managed git worktrees."""

from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, IntPrompt

from config.defaults import WORKTREE_BASE_DIR
from ralph_focus.git_ops import git, worktree_list_paths


def worktree_prune_clean(workspace: Path, *, force: bool, console: Console) -> int:
    paths = worktree_list_paths(workspace)
    if not paths:
        console.print("[red]No worktrees reported (not a git repo?).[/red]")
        return 1
    primary = Path(paths[0])
    removed = skipped_dirty = skipped_missing = 0
    for wt_str in paths[1:]:
        wt = Path(wt_str)
        if not wt.exists():
            console.print(f"[yellow]skip missing:[/yellow] {wt}")
            skipped_missing += 1
            continue
        code, out, _ = git(wt, "status", "--porcelain")
        if code == 0 and out.strip() and not force:
            console.print(f"[yellow]skip dirty:[/yellow] {wt}")
            skipped_dirty += 1
            continue
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(wt))
        rc, _, err = git(workspace, *args)
        if rc != 0:
            console.print(f"[red]failed {wt}:[/red] {err}")
            return 1
        console.print(f"[green]removed:[/green] {wt}")
        removed += 1
    git(workspace, "worktree", "prune")
    console.print(
        f"summary: removed={removed} skipped_dirty={skipped_dirty} "
        f"skipped_missing={skipped_missing} primary={primary}"
    )
    return 0


def list_ralph_managed(workspace: Path) -> list[Path]:
    pat = re.compile(rf"/{re.escape(WORKTREE_BASE_DIR)}/")
    return [Path(p) for p in worktree_list_paths(workspace) if pat.search(p)]


def worktree_remove_interactive(workspace: Path, console: Console) -> int:
    candidates = list_ralph_managed(workspace)
    if not candidates:
        console.print(f"No worktrees under */{WORKTREE_BASE_DIR}/ found.")
        return 0
    for i, p in enumerate(candidates, 1):
        console.print(f"  {i}) {p}")
    idx = IntPrompt.ask("Choose index", default=1) - 1
    if idx < 0 or idx >= len(candidates):
        idx = 0
    selected = candidates[idx]
    code, out, _ = git(selected, "status", "--porcelain")
    force = bool(out.strip())
    if force:
        if not Confirm.ask(f"Force-remove dirty worktree {selected}?", default=False):
            console.print("Aborted.")
            return 1
    else:
        if not Confirm.ask(f"Remove worktree {selected}?", default=False):
            console.print("Aborted.")
            return 0
    args = ["worktree", "remove", str(selected)]
    if force:
        args.insert(2, "-f")
    rc, _, err = git(workspace, *args)
    if rc != 0:
        console.print(f"[red]{err}[/red]")
        return 1
    git(workspace, "worktree", "prune")
    console.print(f"[green]Removed {selected}[/green]")
    return 0
