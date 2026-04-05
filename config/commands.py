"""Config-backed command templates for Sponte verification and git steps."""

from __future__ import annotations

import os
from pathlib import Path


def _split_command_list(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(";;") if part.strip())


VERIFY_COMMANDS: tuple[str, ...] = _split_command_list(
    os.environ.get("RALPH_VERIFY_COMMANDS", "python -m ralph_focus.smoke_tests")
)


def resolved_verify_commands(primary: Path | None = None) -> tuple[str, ...]:
    """Workspace ``commands.verify`` wins; otherwise ``RALPH_VERIFY_COMMANDS``."""
    if primary is not None:
        from ralph_focus.workspace_settings import load_workspace_settings

        v = load_workspace_settings(primary).commands.verify
        if v:
            return v
    return VERIFY_COMMANDS


def verify_commands_markdown(primary: Path | None = None) -> str:
    cmds = resolved_verify_commands(primary)
    if not cmds:
        return "- `(no verification commands configured)`"
    return "\n".join(f"- `{cmd}`" for cmd in cmds)


def git_status_porcelain_args() -> tuple[str, ...]:
    return ("status", "--porcelain")


def git_add_all_args() -> tuple[str, ...]:
    return ("add", "-A")


def git_diff_cached_quiet_args() -> tuple[str, ...]:
    return ("diff", "--cached", "--quiet")


def git_checkout_branch_args(branch: str) -> tuple[str, ...]:
    return ("checkout", branch)


def git_merge_feature_args(branch: str, message: str) -> tuple[str, ...]:
    return ("merge", "--no-ff", "-m", message, branch)


def git_merge_abort_args() -> tuple[str, ...]:
    return ("merge", "--abort")


def git_commit_no_edit_args() -> tuple[str, ...]:
    return ("commit", "--no-edit")


def git_verify_ref_args(ref: str) -> tuple[str, ...]:
    return ("rev-parse", "-q", "--verify", ref)
