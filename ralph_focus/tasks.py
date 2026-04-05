"""Task files, priorities, checklist helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from config.defaults import LEGACY_TASKS_DIR, TASKS_DIR

_LEGACY_TASKS_PREFIX = ".tasks/"
_TASK_STAGES = ("backlog", "in-progress", "review-required", "completed")

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


def task_rel_path(stage: str, name: str) -> str:
    return f"{TASKS_DIR}/{stage}/{name}"


def task_file_path(repo: Path, stage: str, name: str) -> Path:
    return repo / TASKS_DIR / stage / name


def legacy_task_file_path(repo: Path, stage: str, name: str) -> Path:
    return repo / LEGACY_TASKS_DIR / stage / name


def priorities_file(repo: Path, filename: str = "priorities.md") -> Path:
    current = repo / TASKS_DIR / filename
    legacy = repo / LEGACY_TASKS_DIR / filename
    if current.exists() or not legacy.exists():
        return current
    return legacy


def task_root(repo: Path) -> str:
    current = repo / TASKS_DIR
    legacy = repo / LEGACY_TASKS_DIR
    if current.exists() or not legacy.exists():
        return TASKS_DIR
    return LEGACY_TASKS_DIR


def task_layout_root(task_rel: str) -> str:
    a = task_rel.removeprefix("./")
    if a.startswith(f"{LEGACY_TASKS_DIR}/") or a.startswith(_LEGACY_TASKS_PREFIX):
        return LEGACY_TASKS_DIR
    return TASKS_DIR


def normalize_task_rel(arg: str) -> str:
    a = arg.removeprefix("./")
    if a.startswith("/"):
        return Path(a).as_posix()
    if a.startswith(f"{LEGACY_TASKS_DIR}/"):
        a = f"{TASKS_DIR}/{a.removeprefix(f'{LEGACY_TASKS_DIR}/')}"
    if a.startswith(_LEGACY_TASKS_PREFIX):
        a = f"{TASKS_DIR}/{a.removeprefix(_LEGACY_TASKS_PREFIX)}"
    prefix = f"{TASKS_DIR}/"
    if a.startswith(prefix):
        return a
    if a.startswith(_TASK_STAGES):
        return f"{TASKS_DIR}/{a}"
    return f"{TASKS_DIR}/{a}"


def task_stage(task_rel: str) -> str | None:
    rel = normalize_task_rel(task_rel)
    prefix = f"{TASKS_DIR}/"
    if not rel.startswith(prefix):
        return None
    remainder = rel.removeprefix(prefix)
    stage = remainder.split("/", maxsplit=1)[0]
    if stage in _TASK_STAGES:
        return stage
    return None


def task_with_stage(task_rel: str, stage: str) -> str:
    a = task_rel.removeprefix("./")
    name = Path(a).name
    return f"{task_layout_root(a)}/{stage}/{name}"


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
        out.append(normalize_task_path(repo, rel))
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
    rel = normalize_task_rel(arg)
    if rel.startswith("/"):
        return Path(rel)
    current = repo / rel
    if current.exists():
        return current
    prefix = f"{TASKS_DIR}/"
    if rel.startswith(prefix):
        legacy_rel = f"{LEGACY_TASKS_DIR}/{rel.removeprefix(prefix)}"
        legacy = repo / legacy_rel
        if legacy.exists():
            return legacy
    return current


def concrete_task_rel(repo: Path, arg: str) -> str:
    path = normalize_task_path(repo, arg)
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return normalize_task_rel(arg)


def slugify_task_stem_for_id(stem: str) -> str:
    """Slug from a task filename stem for ``task_id`` prefix."""
    s = stem.strip().lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    return s.strip("-") or "task"


def task_title_hash_suffix(title: str, *, length: int = 6) -> str:
    """Stable hex suffix from task title only (``task_id`` uniqueness)."""
    return hashlib.sha256(title.strip().encode("utf-8")).hexdigest()[:length]


def compute_task_id(*, task_stem: str, task_title: str) -> str:
    """
    ``task_id = <slugified-stem>-<6charhash(title)>``.

    Changing the task title changes the id; stem comes from the markdown filename.
    """
    stem = Path(task_stem).stem if task_stem.strip() else "task"
    slug = slugify_task_stem_for_id(stem)
    return f"{slug}-{task_title_hash_suffix(task_title)}"
