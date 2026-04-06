from pathlib import Path

from config.defaults import LEGACY_TASKS_DIR, TASKS_DIR


def test_sponte_tasks_layout_valid_without_priorities_md(tmp_path: Path) -> None:
    from ralph_focus.workspace_tasks import sponte_tasks_layout_valid

    root = tmp_path / "r"
    (root / TASKS_DIR).mkdir(parents=True)
    assert sponte_tasks_layout_valid(root)


def test_task_path_helpers_build_workspace_paths(tmp_path: Path) -> None:
    from ralph_focus.tasks import task_file_path, task_rel_path

    assert task_rel_path("backlog", "demo.md") == f"{TASKS_DIR}/backlog/demo.md"
    assert task_file_path(tmp_path, "completed", "demo.md") == tmp_path / TASKS_DIR / "completed" / "demo.md"


def test_normalize_task_rel_maps_legacy_and_shorthand_paths() -> None:
    from ralph_focus.tasks import normalize_task_rel

    assert normalize_task_rel(".tasks/backlog/demo.md") == f"{TASKS_DIR}/backlog/demo.md"
    assert normalize_task_rel("backlog/demo.md") == f"{TASKS_DIR}/backlog/demo.md"
    assert normalize_task_rel(f"{TASKS_DIR}/in-progress/demo.md") == f"{TASKS_DIR}/in-progress/demo.md"


def test_task_stage_helpers_classify_and_retarget_paths() -> None:
    from ralph_focus.tasks import task_rel_path, task_stage, task_with_stage

    rel = task_rel_path("backlog", "demo.md")

    assert task_stage(rel) == "backlog"
    assert task_with_stage(rel, "in-progress") == f"{TASKS_DIR}/in-progress/demo.md"


def test_normalize_task_path_falls_back_to_existing_legacy_task_file(tmp_path: Path) -> None:
    from ralph_focus.tasks import normalize_task_path

    legacy_task = tmp_path / LEGACY_TASKS_DIR / "backlog" / "demo.md"
    legacy_task.parent.mkdir(parents=True, exist_ok=True)
    legacy_task.write_text("- [ ] legacy\n", encoding="utf-8")

    assert normalize_task_path(tmp_path, "backlog/demo.md") == legacy_task


def test_compute_task_id_uses_title_slug_and_title_hash() -> None:
    from ralph_focus.tasks import compute_task_id, task_title_hash_suffix

    tid = compute_task_id(task_stem="internal-file-name", task_title="Add OAuth login")
    assert tid.startswith("add-oauth-login-")
    assert len(tid.split("-")[-1]) == 6
    assert task_title_hash_suffix("Add OAuth login") == tid.rsplit("-", 1)[-1]


def test_pending_selectable_task_paths_include_any_markdown_not_locked(tmp_path: Path) -> None:
    from ralph_focus.tasks import pending_selectable_task_paths
    from ralph_focus.tasks_lock_registry import tasks_lock_append

    task_a = tmp_path / TASKS_DIR / "alpha.md"
    task_b = tmp_path / TASKS_DIR / "nested" / "beta.md"
    ignored_tmp = tmp_path / TASKS_DIR / "_tmp" / "helper.md"
    ignored_artifact = tmp_path / TASKS_DIR / "artifacts" / "old.md"

    task_a.parent.mkdir(parents=True, exist_ok=True)
    task_b.parent.mkdir(parents=True, exist_ok=True)
    ignored_tmp.parent.mkdir(parents=True, exist_ok=True)
    ignored_artifact.parent.mkdir(parents=True, exist_ok=True)

    task_a.write_text("# Alpha\n\nNo checklist.\n", encoding="utf-8")
    task_b.write_text("# Beta\n\nNested task.\n", encoding="utf-8")
    ignored_tmp.write_text("# temp\n", encoding="utf-8")
    ignored_artifact.write_text("# artifact\n", encoding="utf-8")

    tasks_lock_append(tmp_path, task_b)

    assert pending_selectable_task_paths(tmp_path) == [task_a]


def test_sponte_job_paths_under_workspace(tmp_path: Path) -> None:
    from ralph_focus.paths import (
        sponte_job_session_dir,
        sponte_job_session_task_dir,
        sponte_job_task_dir,
        sponte_jobs_root,
        workspace_task_claim_lock_path,
    )

    root = tmp_path / "repo"
    assert sponte_jobs_root(root) == root / ".sponte" / "jobs"
    assert sponte_job_task_dir(root, "feat-abc123") == root / ".sponte" / "jobs" / "tasks" / "feat-abc123"
    assert sponte_job_session_dir(root, "rap-deadbeef") == root / ".sponte" / "jobs" / "sessions" / "rap-deadbeef"
    assert sponte_job_session_task_dir(root, "rap-x", "feat-abc123") == (
        root / ".sponte" / "jobs" / "sessions" / "rap-x" / "tasks" / "feat-abc123"
    )
    assert workspace_task_claim_lock_path(root, "feat-abc123") == (
        root / ".sponte" / "locks" / "tasks" / "feat-abc123.lock"
    )
