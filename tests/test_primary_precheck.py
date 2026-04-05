from pathlib import Path

from config.defaults import SPONTE_GUARDRAILS_PATH, SPONTE_PROGRESS_PATH, WORKTREE_BASE_DIR
from ralph_focus.primary_precheck import PrimaryPrecheckKind, merge_precheck_classify_porcelain


def test_merge_precheck_ignores_any_path_under_dot_sponte() -> None:
    porcelain = "?? .sponte/tasks/backlog/example.md"

    result = merge_precheck_classify_porcelain(porcelain, merge_head=False)

    assert result.kind is PrimaryPrecheckKind.CLEAN


def test_merge_precheck_ignores_repo_local_sponte_state() -> None:
    porcelain = "\n".join(
        [
            f"?? {WORKTREE_BASE_DIR}/raf-demo",
            f"?? {SPONTE_GUARDRAILS_PATH}",
            f"?? {SPONTE_PROGRESS_PATH}",
        ]
    )

    result = merge_precheck_classify_porcelain(porcelain, merge_head=False)

    assert result.kind is PrimaryPrecheckKind.CLEAN


def test_merge_precheck_ignores_custom_configured_worktree_root() -> None:
    porcelain = "?? .sponte/custom-worktrees/raf-demo"

    result = merge_precheck_classify_porcelain(
        porcelain,
        merge_head=False,
        worktree_root=".sponte/custom-worktrees",
    )

    assert result.kind is PrimaryPrecheckKind.CLEAN


def test_gitignore_ignores_repo_local_sponte_state() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    text = (repo_root / ".gitignore").read_text(encoding="utf-8")

    assert ".sponte/" in text
