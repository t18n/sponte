"""Task files, priorities, checklist helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from config.defaults import TASKS_DIR

_LEGACY_TASKS_PREFIX = ".tasks/"

_PENDING = re.compile(r"^[\s]*([-*]|[0-9]+\.)[\s]+\[[\s]\]", re.MULTILINE)
_DONE = re.compile(r"^[\s]*([-*]|[0-9]+\.)[\s]+\[x\]", re.MULTILINE)
_PRIORITY_LINK = re.compile(r"\]\(\./(backlog|in-progress)/([^)]+\.md)\)")
_TASK_LINE = re.compile(r"^task:\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class TaskSnapshot:
    text: str
    pending: int
    done: int
    label: str


_TASK_CACHE: dict[Path, tuple[tuple[int, int], TaskSnapshot]] = {}
_PRIORITIES_CACHE: dict[Path, tuple[tuple[int, int], list[Path]]] = {}


def _mtime_key(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def clear_task_cache() -> None:
    _TASK_CACHE.clear()
    _PRIORITIES_CACHE.clear()


def task_snapshot(path: Path) -> TaskSnapshot:
    if not path.is_file():
        return TaskSnapshot(text="", pending=0, done=0, label="task")
    key = _mtime_key(path)
    cached = _TASK_CACHE.get(path)
    if cached and cached[0] == key:
        return cached[1]
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _TASK_LINE.search(text)
    if m:
        label = m.group(1).strip().strip('"').strip("'")
        label = label[:200] if label else path.stem.replace("-", " ")
    else:
        label = path.stem.replace("-", " ")
    snap = TaskSnapshot(
        text=text,
        pending=len(_PENDING.findall(text)),
        done=len(_DONE.findall(text)),
        label=label,
    )
    _TASK_CACHE[path] = (key, snap)
    return snap


def count_checklist(path: Path) -> tuple[int, int]:
    snap = task_snapshot(path)
    return snap.pending, snap.done


def task_has_pending(path: Path) -> bool:
    return task_snapshot(path).pending > 0


def priority_task_paths(priorities_file: Path, repo: Path) -> list[Path]:
    if not priorities_file.is_file():
        return []
    key = _mtime_key(priorities_file)
    cached = _PRIORITIES_CACHE.get(priorities_file)
    if cached and cached[0] == key:
        return cached[1]
    text = priorities_file.read_text(encoding="utf-8", errors="replace")
    out: list[Path] = []
    for m in _PRIORITY_LINK.finditer(text):
        rel = f"{m.group(1)}/{m.group(2)}"
        out.append(repo / TASKS_DIR / rel)
    _PRIORITIES_CACHE[priorities_file] = (key, out)
    return out


def select_task_from_priorities(priorities_file: Path, repo: Path) -> Path | None:
    for p in priority_task_paths(priorities_file, repo):
        if p.is_file() and task_has_pending(p):
            return p
    return None


def priority_task_paths_pending(priorities_file: Path, repo: Path) -> list[Path]:
    """All priority-linked tasks that exist and still have pending checklist items."""
    out: list[Path] = []
    for p in priority_task_paths(priorities_file, repo):
        if p.is_file() and task_has_pending(p):
            out.append(p)
    return out


def task_label(path: Path) -> str:
    return task_snapshot(path).label


def normalize_task_path(repo: Path, arg: str) -> Path:
    a = arg.removeprefix("./")
    if a.startswith("/"):
        return Path(a)
    if a.startswith(_LEGACY_TASKS_PREFIX):
        a = f"{TASKS_DIR}/{a.removeprefix(_LEGACY_TASKS_PREFIX)}"
    prefix = f"{TASKS_DIR}/"
    if a.startswith(prefix):
        return repo / a
    if a.startswith(("backlog/", "in-progress/", "completed/")):
        return repo / TASKS_DIR / a
    return repo / TASKS_DIR / a
