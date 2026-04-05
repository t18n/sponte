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


def git_primary_checkout_root(start: Path | None = None) -> Path | None:
    """Primary checkout root for this repository, even when called inside a linked worktree."""
    cwd = start or Path.cwd()
    code, out, _ = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if code != 0:
        code, out, _ = git(cwd, "rev-parse", "--git-common-dir")
        if code != 0:
            return None
    common_dir = Path(out.strip())
    if not common_dir.is_absolute():
        common_dir = (cwd / common_dir).resolve()
    else:
        common_dir = common_dir.resolve()
    if common_dir.name == ".git":
        return common_dir.parent
    return git_toplevel(cwd)


def bootstrap_base_ref(primary: Path) -> str:
    """Pick a local branch to base new trunk branches on (main/master/HEAD), independent of workspace settings."""
    for name in ("main", "master"):
        code, _, _ = git(primary, "show-ref", "--verify", "--quiet", f"refs/heads/{name}")
        if code == 0:
            return name
    code, out, _ = git(primary, "symbolic-ref", "-q", "--short", "HEAD")
    if code == 0 and out.strip():
        return out.strip()
    return "main"


def default_branch_ref(primary: Path) -> str:
    """Legacy name: same as :func:`bootstrap_base_ref`."""
    return bootstrap_base_ref(primary)


def ensure_local_branch(primary: Path, branch: str, base_ref: str) -> tuple[int, str]:
    """Create *branch* at *base_ref* if missing. Returns (0, branch) or (rc, stderr)."""
    code, _, _ = git(primary, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    if code == 0:
        return (0, "")
    rc, _, err = git(primary, "branch", branch, base_ref)
    if rc != 0:
        return (rc, err or "")
    return (0, "")


def trunk_branch_ref(
    primary: Path,
    *,
    trunk_name: str,
    base_ref: str | None = None,
) -> str:
    """Resolve trunk branch name, creating *trunk_name* from *base_ref* when absent."""
    base = base_ref if base_ref is not None else bootstrap_base_ref(primary)
    rc, err = ensure_local_branch(primary, trunk_name, base)
    if rc != 0:
        raise RuntimeError(f"could not ensure trunk branch {trunk_name!r}: {err.strip()}")
    return trunk_name


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
