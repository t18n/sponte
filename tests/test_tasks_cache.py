from pathlib import Path

from ralph_focus.tasks import clear_task_cache, task_snapshot


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_task_snapshot_invalidates_when_file_changes(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    _write(task, 'task: "Initial"\n- [ ] first\n')
    clear_task_cache()

    first = task_snapshot(task)
    assert first.label == "Initial"
    assert first.pending == 1
    assert first.done == 0

    _write(task, 'task: "Updated"\n- [x] first\n- [ ] second\n')
    second = task_snapshot(task)

    assert second.label == "Updated"
    assert second.pending == 1
    assert second.done == 1
