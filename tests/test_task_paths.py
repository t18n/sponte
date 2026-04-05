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
