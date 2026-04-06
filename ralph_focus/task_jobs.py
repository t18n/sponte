"""Repo-local task/session job metadata under ``.sponte/jobs/``."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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
    updated_at: str = ""
    display_name: str = ""
    ai_summary: str = ""
    display_name_source: str = ""
    completed: bool = False
    cleanup_pending: bool = False
    review_required: bool = False
    naming_content_hash: str = ""
    artifacts: list[dict[str, str]] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["updated_at"] = _utc_now()
        if not d.get("artifacts"):
            d.pop("artifacts", None)
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
    updated_at: str = ""

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


def append_task_job_artifact(
    repo: Path,
    task_id: str,
    entry: dict[str, str],
) -> None:
    """Append a manifest entry if ``task_id`` job exists; skip duplicate ``archive_name``."""
    st = read_task_job_status(repo, task_id)
    if st is None:
        return
    archive_name = (entry.get("archive_name") or "").strip()
    if not archive_name:
        return
    if any((e.get("archive_name") or "").strip() == archive_name for e in st.artifacts):
        return
    clean = {str(k): str(v) for k, v in entry.items() if isinstance(k, str) and isinstance(v, str)}
    if not clean:
        return
    arts = list(st.artifacts)
    arts.append(clean)
    write_task_job_status(
        repo,
        TaskJobStatus(
            schema_version=st.schema_version,
            task_id=st.task_id,
            rel_task=st.rel_task,
            stage=st.stage,
            owning_session_id=st.owning_session_id,
            worktree_path=st.worktree_path,
            branch=st.branch,
            task_title=st.task_title,
            updated_at=st.updated_at,
            display_name=st.display_name,
            ai_summary=st.ai_summary,
            display_name_source=st.display_name_source,
            completed=st.completed,
            cleanup_pending=st.cleanup_pending,
            review_required=st.review_required,
            naming_content_hash=st.naming_content_hash,
            artifacts=arts,
        ),
    )


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
        arts: list[dict[str, str]] = []
        raw_arts = raw.get("artifacts")
        if isinstance(raw_arts, list):
            for item in raw_arts:
                if isinstance(item, dict):
                    kd = {str(k): str(v) for k, v in item.items() if isinstance(k, str)}
                    if kd:
                        arts.append(kd)
        return TaskJobStatus(
            schema_version=int(raw.get("schema_version", 1)),
            task_id=str(raw.get("task_id", "")),
            rel_task=str(raw.get("rel_task", "")),
            stage=str(raw.get("stage", "")),
            owning_session_id=str(raw.get("owning_session_id", "")),
            worktree_path=str(raw.get("worktree_path", "")),
            branch=str(raw.get("branch", "")),
            task_title=str(raw.get("task_title", "")),
            updated_at=str(raw.get("updated_at", "")),
            display_name=str(raw.get("display_name", "")),
            ai_summary=str(raw.get("ai_summary", "")),
            display_name_source=str(raw.get("display_name_source", "")),
            completed=bool(raw.get("completed", False)),
            cleanup_pending=bool(raw.get("cleanup_pending", False)),
            review_required=bool(raw.get("review_required", False)),
            naming_content_hash=str(raw.get("naming_content_hash", "")),
            artifacts=arts,
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
            updated_at=str(raw.get("updated_at", "")),
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
