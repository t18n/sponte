"""Thin git wrappers (list argv, no shell)."""

from __future__ import annotations

from pathlib import Path

from ralph_focus.guardrails.subprocess import run_checked


def git(
    cwd: Path,
    *args: str,
    stdin: int | None = None,
) -> tuple[int, str, str]:
    argv = ["git", *args]
    kw: dict = {"cwd": cwd}
    if stdin is not None:
        kw["stdin"] = stdin
    p = run_checked(argv, **kw)
    return p.returncode, p.stdout or "", p.stderr or ""


def git_toplevel(start: Path | None = None) -> Path | None:
    cwd = start or Path.cwd()
    code, out, _ = git(cwd, "rev-parse", "--show-toplevel")
    if code != 0:
        return None
    return Path(out.strip())


def default_branch_ref(primary: Path) -> str:
    for name in ("main", "master"):
        code, _, _ = git(primary, "show-ref", "--verify", "--quiet", f"refs/heads/{name}")
        if code == 0:
            return name
    code, out, _ = git(primary, "symbolic-ref", "-q", "--short", "HEAD")
    if code == 0 and out.strip():
        return out.strip()
    return "main"


def worktree_list_paths(primary: Path) -> list[str]:
    code, out, _ = git(primary, "worktree", "list", "--porcelain")
    if code != 0:
        return []
    paths: list[str] = []
    for line in out.splitlines():
        if line.startswith("worktree "):
            paths.append(line[9:].strip())
    return paths


def worktree_registered(primary: Path, wt: Path) -> bool:
    resolved = str(wt.resolve())
    return resolved in {Path(p).resolve().as_posix() for p in worktree_list_paths(primary)}
