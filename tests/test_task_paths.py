from pathlib import Path

from config.defaults import LEGACY_TASKS_DIR, TASKS_DIR


def test_task_path_helpers_build_workspace_paths(tmp_path: Path) -> None:
    from ralph_focus.tasks import priorities_file, task_file_path, task_rel_path

    assert priorities_file(tmp_path) == tmp_path / TASKS_DIR / "priorities.md"
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


def test_priority_task_paths_pending_falls_back_to_legacy_layout(tmp_path: Path) -> None:
    from ralph_focus.tasks import priorities_file, priority_task_paths_pending

    legacy_task = tmp_path / LEGACY_TASKS_DIR / "backlog" / "demo.md"
    legacy_task.parent.mkdir(parents=True, exist_ok=True)
    legacy_task.write_text("- [ ] legacy\n", encoding="utf-8")
    legacy_priorities = tmp_path / LEGACY_TASKS_DIR / "priorities.md"
    legacy_priorities.parent.mkdir(parents=True, exist_ok=True)
    legacy_priorities.write_text("- [Demo](./backlog/demo.md)\n", encoding="utf-8")

    assert priority_task_paths_pending(priorities_file(tmp_path), tmp_path) == [legacy_task]


def test_compute_task_id_uses_stem_and_title_hash() -> None:
    from ralph_focus.tasks import compute_task_id, task_title_hash_suffix

    tid = compute_task_id(task_stem="add-login", task_title="Add OAuth login")
    assert tid.startswith("add-login-")
    assert len(tid.split("-")[-1]) == 6
    assert task_title_hash_suffix("Add OAuth login") == tid.rsplit("-", 1)[-1]


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
