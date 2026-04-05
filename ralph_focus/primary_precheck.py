"""Classify primary checkout state before Ralph merges the feature branch into main."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from config.defaults import LEGACY_RALPH_DATA_DIR, SPONTE_GUARDRAILS_PATH, SPONTE_PROGRESS_PATH, WORKTREE_BASE_DIR
from ralph_focus.git_ops import git


class PrimaryPrecheckKind(Enum):
    CLEAN = "clean"
    REBASE_IN_PROGRESS = "rebase_in_progress"
    CONFLICT_DIRTY = "conflict_dirty"
    OTHER_DIRTY = "other_dirty"


@dataclass(frozen=True)
class PrimaryPrecheckResult:
    kind: PrimaryPrecheckKind
    detail: str


def _porcelain_path(line: str) -> str:
    if len(line) < 4:
        return ""
    path_part = line[3:].strip()
    if " -> " in path_part:
        path_part = path_part.split(" -> ", maxsplit=1)[-1].strip()
    return path_part


def _ignored_for_merge_precheck(path_part: str) -> bool:
    ignored_prefixes = (
        f"{LEGACY_RALPH_DATA_DIR}/",
        ".ralph/",
        f"{WORKTREE_BASE_DIR}/",
    )
    ignored_exact = {
        SPONTE_GUARDRAILS_PATH,
        SPONTE_PROGRESS_PATH,
    }
    return path_part.startswith(ignored_prefixes) or path_part in ignored_exact


def _porcelain_unmerged(line: str) -> bool:
    """True if git short status indicates an unmerged entry (merge/cherry-pick conflicts)."""
    if not line:
        return False
    if line.startswith("??") or line.startswith("!!"):
        return False
    if len(line) < 2:
        return False
    x, y = line[0], line[1]
    if x == "U" or y == "U":
        return True
    pair = x + y
    return pair in frozenset({"DD", "AA", "AU", "UA", "DU", "UD"})


def rebase_in_progress(primary: Path) -> bool:
    code, _, _ = git(primary, "rev-parse", "-q", "--verify", "REBASE_HEAD")
    return code == 0


def merge_in_progress(primary: Path) -> bool:
    code, _, _ = git(primary, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    return code == 0


def is_branch_merged_into(primary: Path, branch: str, main_ref: str) -> bool:
    """True if ``branch`` tip is an ancestor of ``main_ref`` (already merged into main)."""
    code, _, _ = git(primary, "merge-base", "--is-ancestor", branch, main_ref)
    return code == 0


def merge_precheck_classify_porcelain(
    porcelain_out: str,
    *,
    merge_head: bool,
    status_failed: bool = False,
) -> PrimaryPrecheckResult:
    """
    Classify from ``git status --porcelain`` text and merge state (no git calls).
    Used by primary_merge_precheck_state and smoke tests.
    """
    if status_failed:
        return PrimaryPrecheckResult(PrimaryPrecheckKind.OTHER_DIRTY, "git status failed on primary")

    non_ignored: list[str] = []
    unmerged_non_ignored = False
    for line in porcelain_out.splitlines():
        if len(line) < 4:
            continue
        path_part = _porcelain_path(line)
        if _ignored_for_merge_precheck(path_part):
            continue
        non_ignored.append(line)
        if _porcelain_unmerged(line):
            unmerged_non_ignored = True

    if not non_ignored and not merge_head:
        return PrimaryPrecheckResult(PrimaryPrecheckKind.CLEAN, "")

    if merge_head or unmerged_non_ignored:
        detail = "\n".join(non_ignored[:20]) if non_ignored else "MERGE_HEAD set (no non-ignored porcelain lines)"
        return PrimaryPrecheckResult(PrimaryPrecheckKind.CONFLICT_DIRTY, detail)

    detail = "\n".join(non_ignored[:20])
    return PrimaryPrecheckResult(PrimaryPrecheckKind.OTHER_DIRTY, detail)


def primary_merge_precheck_state(primary: Path) -> PrimaryPrecheckResult:
    """
    Classify primary working tree for merge precheck.

    CONFLICT_DIRTY: MERGE_HEAD and/or unmerged porcelain outside ignored paths, or MERGE_HEAD with
    no non-ignored porcelain (rare; merge must still be completed).
    """
    if rebase_in_progress(primary):
        return PrimaryPrecheckResult(
            PrimaryPrecheckKind.REBASE_IN_PROGRESS,
            "git rebase in progress (REBASE_HEAD). Finish or abort the rebase, then retry.",
        )

    has_merge_head = merge_in_progress(primary)
    code, out, _ = git(primary, "status", "--porcelain")
    return merge_precheck_classify_porcelain(out, merge_head=has_merge_head, status_failed=(code != 0))
