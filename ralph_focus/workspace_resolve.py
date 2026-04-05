"""Resolve the git workspace root (Sponte primary checkout) from CLI or prompts."""

from __future__ import annotations

import os
import shlex
from dataclasses import replace
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from config.defaults import DEFAULT_EXECUTE_MODEL, DEFAULT_PLAN_MODEL

from ralph_focus.git_ops import git_primary_checkout_root
from ralph_focus.workspace_settings import (
    CustomHarnessConfig,
    WorkspacePolicy,
    load_workspace_settings,
    save_workspace_settings,
)
from ralph_focus.interactive_setup import resolve_choice_index
from ralph_focus.workspace_init import init_sponte_workspace
from ralph_focus.workspace_tasks import sponte_tasks_layout_valid
from ralph_focus.workspaces_registry import load_known_workspaces, register_workspace

BUILTIN_HARNESS_IDS: tuple[str, ...] = ("cursor", "claude", "codex", "droid", "oz", "warp", "amp")


def _interactive_execution_settings(*, primary: Path, console: Console) -> None:
    """Prompt for harness/models, probe, then write ``.sponte/settings.json``."""
    from ralph_focus.init_harness_probe import probe_init_harness_selection

    if os.environ.get("SPONTE_INIT_SKIP_HARNESS_PROBE", "").lower() in ("1", "true", "yes"):
        return

    while True:
        table = Table(title="Default harness (headless CLI)")
        table.add_column("#")
        table.add_column("Harness")
        for idx, hid in enumerate(BUILTIN_HARNESS_IDS, start=1):
            table.add_row(str(idx), hid)
        table.add_row("c", "custom (your CLI on PATH)")
        console.print(table)
        choice = Prompt.ask("Choose harness", default="1").strip().lower()
        custom_cfg: CustomHarnessConfig | None = None
        harness_field = ""
        if choice in ("c", "custom"):
            harness_field = "custom"
            exe = Prompt.ask("Executable name (on PATH)").strip()
            if not exe:
                console.print("[red]Executable is required for custom harness.[/red]")
                continue
            args_raw = Prompt.ask("Fixed args before prompt (shlex, optional)", default="").strip()
            probe_raw = Prompt.ask(
                "Probe command (shlex, optional, e.g. `mycli --version`)",
                default="",
            ).strip()
            args_t = tuple(shlex.split(args_raw)) if args_raw else ()
            probe_t = tuple(shlex.split(probe_raw)) if probe_raw else ()
            custom_cfg = CustomHarnessConfig(executable=exe, args=args_t, probe=probe_t)
        else:
            try:
                n = int(choice)
                if n < 1 or n > len(BUILTIN_HARNESS_IDS):
                    raise IndexError
                harness_field = BUILTIN_HARNESS_IDS[n - 1]
            except (ValueError, IndexError):
                console.print(f"[red]Invalid choice; enter 1–{len(BUILTIN_HARNESS_IDS)} or c.[/red]")
                continue

        pm = Prompt.ask("Plan model", default=DEFAULT_PLAN_MODEL).strip() or DEFAULT_PLAN_MODEL
        em = Prompt.ask("Execute model", default=DEFAULT_EXECUTE_MODEL).strip() or DEFAULT_EXECUTE_MODEL
        mpr_raw = IntPrompt.ask("Max phase rounds (backpressure)", default=20)
        try:
            mpr = max(1, int(mpr_raw))
        except (TypeError, ValueError):
            mpr = 20

        err = probe_init_harness_selection(
            primary,
            harness_id=harness_field,
            plan_model=pm,
            execute_model=em,
            custom=custom_cfg,
        )
        if err:
            console.print(f"[red]Validation failed:[/red] {err}")
            console.print("[yellow]Try another harness or model string.[/yellow]")
            continue

        cur = load_workspace_settings(primary)
        new_policy = WorkspacePolicy(
            max_phase_rounds=mpr,
            verification_required=cur.policy.verification_required,
            merge_required=cur.policy.merge_required,
        )
        save_workspace_settings(
            primary,
            replace(
                cur,
                harness=harness_field,
                plan_model=pm,
                execute_model=em,
                custom_harness=custom_cfg if harness_field == "custom" else None,
                policy=new_policy,
            ),
        )
        console.print("[green]Saved workspace execution settings to[/green] `.sponte/settings.json`")
        return


def resolve_git_repo_root(
    workspace: Path | None,
    *,
    console: Console,
    interactive: bool,
    prompt_label: str = "Repository",
) -> Path:
    """Resolve a git checkout root (no Sponte tasks validation)."""
    if workspace is not None:
        candidate = workspace.expanduser().resolve()
        root = git_primary_checkout_root(candidate)
        if root is None:
            console.print(f"[red]{prompt_label}: not a git repository:[/red] {candidate}")
            raise typer.Exit(1)
        register_workspace(root)
        return root

    cwd_root = git_primary_checkout_root(Path.cwd())
    if cwd_root is not None:
        register_workspace(cwd_root)
        return cwd_root

    if not interactive:
        console.print("[red]Not inside a git repository; use --workspace PATH.[/red]")
        raise typer.Exit(1)

    return _prompt_workspace(console, prompt_label=prompt_label)


def resolve_primary_workspace(
    workspace: Path | None,
    *,
    console: Console,
    interactive: bool,
    prompt_label: str = "Workspace",
) -> Path:
    """
    Git root plus a valid ``.sponte/tasks`` layout (unless *interactive* prompts for another root).
    """
    if workspace is not None:
        return _require_valid_tasks(
            resolve_git_repo_root(workspace, console=console, interactive=interactive, prompt_label=prompt_label),
            console=console,
            interactive=interactive,
            prompt_label=prompt_label,
        )

    cwd_root = git_primary_checkout_root(Path.cwd())
    if cwd_root is not None and sponte_tasks_layout_valid(cwd_root):
        register_workspace(cwd_root)
        return cwd_root

    if not interactive:
        if cwd_root is None:
            console.print("[red]Not inside a git repository; use --workspace PATH.[/red]")
            raise typer.Exit(1)
        console.print(
            f"[red]{prompt_label}: `.sponte/tasks` is missing or invalid; "
            f"run `sponte init` first.[/red]"
        )
        raise typer.Exit(1)

    picked = _prompt_workspace(console, prompt_label=prompt_label)
    return _require_valid_tasks(picked, console=console, interactive=True, prompt_label=prompt_label)


def _require_valid_tasks(
    root: Path,
    *,
    console: Console,
    interactive: bool,
    prompt_label: str,
) -> Path:
    if sponte_tasks_layout_valid(root):
        return root
    if not interactive:
        console.print(
            f"[red]{prompt_label}: `.sponte/tasks` is missing or invalid; "
            f"run `sponte init` first.[/red]"
        )
        raise typer.Exit(1)
    console.print(f"[yellow]{root} does not have a valid `.sponte/tasks` layout; pick another workspace.[/yellow]")
    return resolve_primary_workspace(None, console=console, interactive=True, prompt_label=prompt_label)


def _prompt_workspace(console: Console, *, prompt_label: str) -> Path:
    known = load_known_workspaces()
    if known:
        table = Table(title=f"{prompt_label} — known workspaces")
        table.add_column("#")
        table.add_column("Path")
        for idx, p in enumerate(known, 1):
            table.add_row(str(idx), str(p))
        console.print(table)
        console.print("Enter a number from the table, or type an absolute path to a git checkout.")
        raw = Prompt.ask("Workspace", default="1")
        raw_stripped = raw.strip()
        if raw_stripped.isdigit():
            try:
                i = resolve_choice_index(choice_count=len(known), raw_index=int(raw_stripped))
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(1) from exc
            chosen = known[i]
            root = git_primary_checkout_root(chosen)
            if root is None:
                console.print(f"[red]Path is not a git repository:[/red] {chosen}")
                raise typer.Exit(1)
            register_workspace(root)
            return root
        path = Path(raw_stripped).expanduser()
    else:
        raw = Prompt.ask(f"{prompt_label} (path to git checkout)")
        path = Path(raw.strip()).expanduser()

    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    root = git_primary_checkout_root(path)
    if root is None:
        console.print(f"[red]Not a git repository:[/red] {path}")
        raise typer.Exit(1)
    register_workspace(root)
    return root


def bootstrap_workspace_with_prompt(
    primary: Path,
    *,
    console: Console,
    interactive: bool,
    trunk_branch: str | None = None,
) -> None:
    if not interactive:
        console.print(
            "[red]`sponte init` requires an interactive terminal (stdin must be a TTY).[/red]"
        )
        raise typer.Exit(1)
    source: Path | None = None
    if Confirm.ask("Migrate tasks from an existing markdown file or folder?", default=False):
        src_raw = Prompt.ask("Source path (file or folder of `.md` tasks)")
        source = Path(src_raw.strip()).expanduser()
        if not source.is_absolute():
            source = (Path.cwd() / source).resolve()
        if not source.exists():
            console.print(f"[red]Source does not exist:[/red] {source}")
            raise typer.Exit(1)
    trunk_raw = trunk_branch if trunk_branch is not None else Prompt.ask(
        "Trunk branch name (created if missing)",
        default="sponte",
    )
    try:
        init_sponte_workspace(primary, source=source, trunk_branch=trunk_raw.strip() or None)
    except (OSError, RuntimeError) as exc:
        console.print(f"[red]Init failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]Initialized Sponte tasks under[/green] {primary / '.sponte'}")
    _interactive_execution_settings(primary=primary, console=console)


def resolve_trunk_branch_ref(primary: Path, *, cli_override: str | None) -> str:
    from ralph_focus.git_ops import trunk_branch_ref
    from ralph_focus.workspace_settings import load_workspace_settings

    if cli_override is not None and cli_override.strip():
        name = cli_override.strip()
    else:
        name = load_workspace_settings(primary).normalized_trunk()
    return trunk_branch_ref(primary, trunk_name=name)


def persist_trunk_branch_override(primary: Path, trunk_branch: str) -> str:
    from ralph_focus.git_ops import trunk_branch_ref

    name = trunk_branch.strip()
    if not name:
        raise ValueError("trunk branch must be non-empty")
    validated = trunk_branch_ref(primary, trunk_name=name)
    save_workspace_settings(primary, replace(load_workspace_settings(primary), trunk_branch=validated))
    return validated


__all__ = [
    "bootstrap_workspace_with_prompt",
    "persist_trunk_branch_override",
    "resolve_git_repo_root",
    "resolve_primary_workspace",
    "resolve_trunk_branch_ref",
]
