"""Repo-local task/session job metadata under ``.sponte/jobs/``."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ralph_focus.paths import sponte_job_session_dir, sponte_job_task_dir


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class TaskJobStatus:
    schema_version: int = 1
    task_id: str = ""
    rel_task: str = ""
    stage: str = "in-progress"
    owning_session_id: str = ""
    worktree_path: str = ""
    branch: str = ""
    task_title: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["updated_at"] = _utc_now()
        return d


@dataclass
class SessionJobStatus:
    schema_version: int = 1
    session_id: str = ""
    workspace_root: str = ""
    active_task_id: str = ""
    rel_task: str = ""
    phase: str = ""
    worktree_path: str = ""
    branch: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["updated_at"] = _utc_now()
        return d


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_task_job_status(repo: Path, status: TaskJobStatus) -> None:
    path = sponte_job_task_dir(repo, status.task_id) / "status.json"
    _write_json(path, status.to_json_dict())


def read_task_job_status(repo: Path, task_id: str) -> TaskJobStatus | None:
    path = sponte_job_task_dir(repo, task_id) / "status.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return TaskJobStatus(
            schema_version=int(raw.get("schema_version", 1)),
            task_id=str(raw.get("task_id", "")),
            rel_task=str(raw.get("rel_task", "")),
            stage=str(raw.get("stage", "")),
            owning_session_id=str(raw.get("owning_session_id", "")),
            worktree_path=str(raw.get("worktree_path", "")),
            branch=str(raw.get("branch", "")),
            task_title=str(raw.get("task_title", "")),
        )
    except (TypeError, ValueError):
        return None


def write_session_job_status(repo: Path, status: SessionJobStatus) -> None:
    path = sponte_job_session_dir(repo, status.session_id) / "status.json"
    _write_json(path, status.to_json_dict())


def read_session_job_status(repo: Path, session_id: str) -> SessionJobStatus | None:
    path = sponte_job_session_dir(repo, session_id) / "status.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return SessionJobStatus(
            schema_version=int(raw.get("schema_version", 1)),
            session_id=str(raw.get("session_id", "")),
            workspace_root=str(raw.get("workspace_root", "")),
            active_task_id=str(raw.get("active_task_id", "")),
            rel_task=str(raw.get("rel_task", "")),
            phase=str(raw.get("phase", "")),
            worktree_path=str(raw.get("worktree_path", "")),
            branch=str(raw.get("branch", "")),
        )
    except (TypeError, ValueError):
        return None


def init_task_job_artifacts(
    repo: Path,
    *,
    task_id: str,
    task_abs: Path,
    session_id: str,
    rel_task: str,
) -> None:
    """Create task job dir with snapshots and ``status.json``."""
    job = sponte_job_task_dir(repo, task_id)
    job.mkdir(parents=True, exist_ok=True)
    (job / "artifacts").mkdir(exist_ok=True)
    (job / "improvements").mkdir(exist_ok=True)
    text = task_abs.read_text(encoding="utf-8", errors="replace")
    (job / "task.original.md").write_text(text, encoding="utf-8")
    (job / "task.md").write_text(text, encoding="utf-8")
    from ralph_focus.tasks import task_label

    title = task_label(task_abs)
    write_task_job_status(
        repo,
        TaskJobStatus(
            task_id=task_id,
            rel_task=rel_task,
            stage="in-progress",
            owning_session_id=session_id,
            task_title=title,
        ),
    )


def touch_session_job_folder(repo: Path, session_id: str) -> Path:
    root = sponte_job_session_dir(repo, session_id)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    return root
