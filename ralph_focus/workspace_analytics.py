"""Append-only per-workspace analytics under ``ralph_data_dir``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ralph_focus.paths import ralph_data_dir


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def analytics_dir(workspace_root: Path) -> Path:
    return ralph_data_dir(workspace_root) / "analytics"


def analytics_summary_path(workspace_root: Path) -> Path:
    return analytics_dir(workspace_root) / "summary.json"


def analytics_events_path(workspace_root: Path) -> Path:
    return analytics_dir(workspace_root) / "events.jsonl"


def _coerce_str_int_dict(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            continue
        try:
            out[k.strip()] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def harness_model_increment_keys(
    harness: str, plan_model: str, execute_model: str
) -> list[str]:
    """Keys ``harness:model`` to bump for one lifecycle event (plan/execute deduped when equal)."""
    h = harness.strip()
    pm = plan_model.strip()
    em = execute_model.strip()
    if not h:
        return []
    if pm and em and pm == em:
        return [f"{h}:{pm}"]
    out: list[str] = []
    if pm:
        out.append(f"{h}:{pm}")
    if em:
        out.append(f"{h}:{em}")
    return out


@dataclass
class AnalyticsSummary:
    sessions_started: int = 0
    sessions_resumed: int = 0
    tasks_completed: int = 0
    tasks_cancelled: int = 0
    tasks_review_required: int = 0
    cleanup_repairs: int = 0
    tasks_claimed: int = 0
    total_task_wall_seconds: float = 0.0
    total_tokens: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    merges_completed: int = 0
    harness_counts: dict[str, int] = field(default_factory=dict)
    harness_model_counts: dict[str, int] = field(default_factory=dict)
    plan_model_counts: dict[str, int] = field(default_factory=dict)
    execute_model_counts: dict[str, int] = field(default_factory=dict)
    workspace_slugs: list[str] = field(default_factory=list)
    updated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "sessions_started": self.sessions_started,
            "sessions_resumed": self.sessions_resumed,
            "tasks_completed": self.tasks_completed,
            "tasks_cancelled": self.tasks_cancelled,
            "tasks_review_required": self.tasks_review_required,
            "cleanup_repairs": self.cleanup_repairs,
            "tasks_claimed": self.tasks_claimed,
            "total_task_wall_seconds": self.total_task_wall_seconds,
            "total_tokens": self.total_tokens,
            "lines_added": self.lines_added,
            "lines_deleted": self.lines_deleted,
            "merges_completed": self.merges_completed,
            "harness_counts": dict(self.harness_counts),
            "harness_model_counts": dict(self.harness_model_counts),
            "plan_model_counts": dict(self.plan_model_counts),
            "execute_model_counts": dict(self.execute_model_counts),
            "workspace_slugs": list(self.workspace_slugs),
            "updated_at": self.updated_at or _utc_iso(),
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> AnalyticsSummary:
        def i(key: str, default: int = 0) -> int:
            try:
                return int(raw.get(key, default))
            except (TypeError, ValueError):
                return default

        def f(key: str, default: float = 0.0) -> float:
            try:
                return float(raw.get(key, default))
            except (TypeError, ValueError):
                return default

        slugs: list[str] = []
        raw_slugs = raw.get("workspace_slugs")
        if isinstance(raw_slugs, list):
            for item in raw_slugs:
                if isinstance(item, str) and item.strip():
                    slugs.append(item.strip())

        return cls(
            sessions_started=i("sessions_started"),
            sessions_resumed=i("sessions_resumed"),
            tasks_completed=i("tasks_completed"),
            tasks_cancelled=i("tasks_cancelled"),
            tasks_review_required=i("tasks_review_required"),
            cleanup_repairs=i("cleanup_repairs"),
            tasks_claimed=i("tasks_claimed"),
            total_task_wall_seconds=f("total_task_wall_seconds"),
            total_tokens=i("total_tokens"),
            lines_added=i("lines_added"),
            lines_deleted=i("lines_deleted"),
            merges_completed=i("merges_completed"),
            harness_counts=_coerce_str_int_dict(raw.get("harness_counts")),
            harness_model_counts=_coerce_str_int_dict(raw.get("harness_model_counts")),
            plan_model_counts=_coerce_str_int_dict(raw.get("plan_model_counts")),
            execute_model_counts=_coerce_str_int_dict(raw.get("execute_model_counts")),
            workspace_slugs=slugs,
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
    payload = summary.to_json()
    # Per-workspace files do not track the cross-workspace slug list.
    payload["workspace_slugs"] = []
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
    try:
        bump_usage_counts(
            workspace_root,
            harness=harness,
            plan_model=plan_model,
            execute_model=execute_model,
        )
    except OSError:
        pass


def append_event(workspace_root: Path, event: dict[str, Any]) -> None:
    p = analytics_events_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = dict(event)
    line.setdefault("timestamp", _utc_iso())
    line.setdefault("workspace", str(workspace_root.resolve()))
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def bump_usage_counts(
    workspace_root: Path,
    *,
    harness: str = "",
    plan_model: str = "",
    execute_model: str = "",
) -> None:
    h = harness.strip()
    pm = plan_model.strip()
    em = execute_model.strip()
    hm_keys = harness_model_increment_keys(h, pm, em)
    if not h and not hm_keys:
        return
    s = load_summary(workspace_root)
    if h:
        s.harness_counts[h] = s.harness_counts.get(h, 0) + 1
    for key in hm_keys:
        s.harness_model_counts[key] = s.harness_model_counts.get(key, 0) + 1
    save_summary(workspace_root, s)
    try:
        from ralph_focus.global_analytics import mirror_bump_usage_counts_global

        mirror_bump_usage_counts_global(
            workspace_root,
            harness=h,
            plan_model=pm,
            execute_model=em,
        )
    except OSError:
        pass


def bump_summary(workspace_root: Path, **counters: int) -> None:
    s = load_summary(workspace_root)
    for k, v in counters.items():
        cur = getattr(s, k, 0)
        setattr(s, k, cur + v)
    save_summary(workspace_root, s)
    try:
        from ralph_focus.global_analytics import mirror_bump_global

        mirror_bump_global(workspace_root, **counters)
    except OSError:
        pass


def add_completion_rollups(
    workspace_root: Path,
    *,
    duration_sec: float,
    token_delta: int,
    lines_added: int,
    lines_deleted: int,
) -> None:
    """Add task-completion aggregates to workspace + global summaries (best-effort)."""
    s = load_summary(workspace_root)
    s.total_task_wall_seconds += max(0.0, float(duration_sec))
    s.total_tokens += max(0, int(token_delta))
    s.lines_added += max(0, int(lines_added))
    s.lines_deleted += max(0, int(lines_deleted))
    save_summary(workspace_root, s)
    try:
        from ralph_focus.global_analytics import add_completion_rollups_global

        add_completion_rollups_global(
            workspace_root,
            duration_sec=duration_sec,
            token_delta=token_delta,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
        )
    except OSError:
        pass


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
    "add_completion_rollups",
    "append_event",
    "emit_lifecycle_event",
    "analytics_dir",
    "bump_summary",
    "bump_usage_counts",
    "harness_model_increment_keys",
    "load_summary",
    "read_recent_events",
    "save_summary",
]
