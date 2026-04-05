"""CLI availability checks before a Ralph run."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.table import Table

from config.defaults import CODEX_EXECUTABLE, DROID_EXECUTABLE, REQUIRE_GH_AUTH
from ralph_focus.git_ops import git_toplevel
from ralph_focus.harness_resolve import resolve_harness

PreflightStatus = Literal["ok", "fail", "skip"]


def _agent_executable_path(agent_id: str) -> str | None:
    a = agent_id.lower().strip()
    if a == "cursor":
        return shutil.which("cursor-agent")
    if a == "claude":
        return shutil.which("claude")
    if a == "codex":
        return shutil.which(CODEX_EXECUTABLE)
    if a == "droid":
        return shutil.which(DROID_EXECUTABLE)
    return None


def _collect_preflight_rows(
    *,
    agent: str,
    workspace_root: Path | None = None,
) -> list[tuple[str, PreflightStatus, str]]:
    rows: list[tuple[str, PreflightStatus, str]] = []

    primary = git_toplevel() or workspace_root
    if primary is None:
        rows.append(
            (
                "Git repository",
                "fail",
                "not inside a git repository (git rev-parse failed)",
            )
        )
    else:
        rows.append(("Git repository", "ok", str(primary)))

    git_bin = shutil.which("git")
    if not git_bin:
        rows.append(("git executable", "fail", "not on PATH"))
    else:
        rows.append(("git executable", "ok", git_bin))

    try:
        harness = resolve_harness(primary, agent)
        label = f"Agent CLI ({harness.id})"
        availability = harness.availability()
        if not availability.available:
            if availability.problems:
                for e in availability.problems:
                    rows.append((label, "fail", e))
            else:
                rows.append((label, "fail", "reported unavailable"))
        elif availability.problems:
            for e in availability.problems:
                rows.append((label, "fail", e))
        else:
            exe = _agent_executable_path(harness.id)
            rows.append((label, "ok", exe or "(on PATH)"))
    except ValueError as e:
        rows.append(("Agent backend", "fail", str(e)))

    if REQUIRE_GH_AUTH:
        gh_bin = shutil.which("gh")
        if not gh_bin:
            rows.append(
                ("GitHub CLI (gh)", "fail", "not on PATH (RALPH_REQUIRE_GH set)"),
            )
        else:
            p = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            )
            if p.returncode != 0:
                rows.append(
                    ("GitHub CLI (gh)", "fail", "not authenticated (run: gh auth login)"),
                )
            else:
                rows.append(("GitHub CLI (gh)", "ok", gh_bin))
    else:
        rows.append(
            ("GitHub CLI (gh)", "skip", "not required (set RALPH_REQUIRE_GH=1 to enforce)"),
        )

    return rows


def _print_preflight_table(console: Console, rows: list[tuple[str, PreflightStatus, str]]) -> None:
    t = Table(title="Preflight checks")
    t.add_column("Check")
    t.add_column("Status")
    t.add_column("Detail")
    for name, st, detail in rows:
        if st == "ok":
            status_cell = "[green]OK[/green]"
        elif st == "fail":
            status_cell = "[red]FAIL[/red]"
        else:
            status_cell = "[dim]skip[/dim]"
        t.add_row(name, status_cell, detail)
    console.print(t)


def run_preflight(
    *,
    agent: str,
    console: Console | None = None,
    verbose: bool = False,
    workspace_root: Path | None = None,
) -> None:
    c = console or Console(stderr=True)
    rows = _collect_preflight_rows(agent=agent, workspace_root=workspace_root)
    failed = [r for r in rows if r[1] == "fail"]

    if verbose:
        _print_preflight_table(c, rows)

    if failed:
        if not verbose:
            t = Table(title="Preflight failed", show_header=False)
            for name, _st, detail in failed:
                t.add_row(f"{name}: {detail}")
            c.print(t)
        raise SystemExit(1)

    if not verbose:
        c.print("[green]Preflight OK[/green]")
    else:
        c.print("[green]Preflight OK[/green]")
