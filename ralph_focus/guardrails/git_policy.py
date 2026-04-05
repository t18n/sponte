"""Allowlisted git subcommand prefixes for orchestrator use."""

from __future__ import annotations

_ALLOWED_PREFIXES: frozenset[tuple[str, ...]] = frozenset(
    {
        ("rev-parse",),
        ("status",),
        ("worktree",),
        ("checkout",),
        ("merge",),
        ("commit",),
        ("add",),
        ("diff",),
        ("mv",),
        ("reset",),
        ("branch",),
        ("config",),
        ("symbolic-ref",),
        ("show-ref",),
        ("merge-base",),
        ("prune",),
    }
)


def assert_git_argv_allowed(argv: list[str]) -> None:
    if not argv or argv[0] != "git":
        raise ValueError("expected git argv")
    sub = tuple(argv[1 : 1 + max(len(p) for p in _ALLOWED_PREFIXES)])
    ok = any(sub[: len(p)] == p for p in _ALLOWED_PREFIXES)
    if not ok:
        raise ValueError(f"git subcommand not allowlisted: {argv[1:3]}")
