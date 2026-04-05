"""Append-only per-workspace analytics under Sponte app state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ralph_focus.app_state_paths import workspace_runtime_root


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def analytics_dir(workspace_root: Path) -> Path:
    return workspace_runtime_root(workspace_root) / "analytics"


def analytics_summary_path(workspace_root: Path) -> Path:
    return analytics_dir(workspace_root) / "summary.json"


def analytics_events_path(workspace_root: Path) -> Path:
    return analytics_dir(workspace_root) / "events.jsonl"


@dataclass
class AnalyticsSummary:
    sessions_started: int = 0
    sessions_resumed: int = 0
    tasks_completed: int = 0
    tasks_cancelled: int = 0
    tasks_review_required: int = 0
    cleanup_repairs: int = 0
    updated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "sessions_started": self.sessions_started,
            "sessions_resumed": self.sessions_resumed,
            "tasks_completed": self.tasks_completed,
            "tasks_cancelled": self.tasks_cancelled,
            "tasks_review_required": self.tasks_review_required,
            "cleanup_repairs": self.cleanup_repairs,
            "updated_at": self.updated_at or _utc_iso(),
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> AnalyticsSummary:
        def i(key: str, default: int = 0) -> int:
            try:
                return int(raw.get(key, default))
            except (TypeError, ValueError):
                return default

        return cls(
            sessions_started=i("sessions_started"),
            sessions_resumed=i("sessions_resumed"),
            tasks_completed=i("tasks_completed"),
            tasks_cancelled=i("tasks_cancelled"),
            tasks_review_required=i("tasks_review_required"),
            cleanup_repairs=i("cleanup_repairs"),
            updated_at=str(raw.get("updated_at", "")),
        )


def load_summary(workspace_root: Path) -> AnalyticsSummary:
    p = analytics_summary_path(workspace_root)
    if not p.is_file():
        return AnalyticsSummary()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return AnalyticsSummary()
    if not isinstance(raw, dict):
        return AnalyticsSummary()
    return AnalyticsSummary.from_json(raw)


def save_summary(workspace_root: Path, summary: AnalyticsSummary) -> None:
    p = analytics_summary_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    summary.updated_at = _utc_iso()
    p.write_text(json.dumps(summary.to_json(), indent=2) + "\n", encoding="utf-8")


def emit_lifecycle_event(
    workspace_root: Path,
    *,
    event: str,
    outcome: str,
    session_id: str = "",
    task_id: str = "",
    duration_sec: float = 0.0,
    cycles: int = 0,
    harness: str = "",
    plan_model: str = "",
    execute_model: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort JSONL append; never raises for analytics I/O failures."""
    payload: dict[str, Any] = {
        "event": event,
        "outcome": outcome,
        "session_id": session_id,
        "task_id": task_id,
        "duration_sec": duration_sec,
        "cycles": cycles,
        "harness": harness,
        "plan_model": plan_model,
        "execute_model": execute_model,
    }
    if metadata:
        payload["metadata"] = metadata
    try:
        append_event(workspace_root, payload)
    except OSError:
        return


def append_event(workspace_root: Path, event: dict[str, Any]) -> None:
    p = analytics_events_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = dict(event)
    line.setdefault("timestamp", _utc_iso())
    line.setdefault("workspace", str(workspace_root.resolve()))
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def bump_summary(workspace_root: Path, **counters: int) -> None:
    s = load_summary(workspace_root)
    for k, v in counters.items():
        cur = getattr(s, k, 0)
        setattr(s, k, cur + v)
    save_summary(workspace_root, s)


@dataclass
class AnalyticsEvent:
    session_id: str = ""
    task_id: str = ""
    event: str = ""
    outcome: str = ""
    duration_sec: float = 0.0
    cycles: int = 0
    harness: str = ""
    plan_model: str = ""
    execute_model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "event": self.event,
            "outcome": self.outcome,
            "duration_sec": self.duration_sec,
            "cycles": self.cycles,
            "harness": self.harness,
            "plan_model": self.plan_model,
            "execute_model": self.execute_model,
        }
        d.update(self.metadata)
        return d


def read_recent_events(workspace_root: Path, *, limit: int = 20) -> list[dict[str, Any]]:
    p = analytics_events_path(workspace_root)
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            out.append(raw)
    return out


__all__ = [
    "AnalyticsEvent",
    "AnalyticsSummary",
    "append_event",
    "emit_lifecycle_event",
    "analytics_dir",
    "bump_summary",
    "load_summary",
    "read_recent_events",
    "save_summary",
]
