from pathlib import Path

from config.defaults import TASKS_DIR
from ralph_focus.cli import task_list_choice_paths


def test_task_list_choice_paths_includes_all_pending_tasks(tmp_path: Path) -> None:
    pending = [tmp_path / TASKS_DIR / "backlog" / f"task-{i}.md" for i in range(20)]

    choices = task_list_choice_paths(tmp_path, pending)

    assert len(choices) == 20
    assert choices[-1] == f"{TASKS_DIR}/backlog/task-19.md"
