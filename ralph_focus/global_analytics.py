"""Machine-global analytics rollup under ``sponte_state_base_dir()/analytics/``."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ralph_focus.app_state_paths import sponte_state_base_dir, workspace_state_slug
from ralph_focus.workspace_analytics import AnalyticsSummary, harness_model_increment_keys


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

_GLOBAL_SUMMARY_NAME = "global_summary.json"
_MAX_WORKSPACE_SLUGS = 256


def global_analytics_dir() -> Path:
    return sponte_state_base_dir() / "analytics"


def global_summary_path() -> Path:
    return global_analytics_dir() / _GLOBAL_SUMMARY_NAME


def load_global_summary() -> AnalyticsSummary:
    p = global_summary_path()
    if not p.is_file():
        return AnalyticsSummary()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return AnalyticsSummary()
    if not isinstance(raw, dict):
        return AnalyticsSummary()
    return AnalyticsSummary.from_json(raw)


def save_global_summary(summary: AnalyticsSummary) -> None:
    p = global_summary_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    summary.updated_at = _utc_iso()
    p.write_text(json.dumps(summary.to_json(), indent=2) + "\n", encoding="utf-8")


def merge_workspace_slug(summary: AnalyticsSummary, workspace_root: Path) -> None:
    try:
        slug = workspace_state_slug(workspace_root)
    except OSError:
        return
    if not slug:
        return
    cur = list(summary.workspace_slugs)
    if slug in cur:
        return
    cur.append(slug)
    if len(cur) > _MAX_WORKSPACE_SLUGS:
        cur = cur[-_MAX_WORKSPACE_SLUGS:]
    summary.workspace_slugs = cur


def mirror_bump_global(workspace_root: Path, **counters: int) -> None:
    """Apply integer counter deltas to global summary (best-effort)."""
    g = load_global_summary()
    for k, v in counters.items():
        cur = getattr(g, k, None)
        if not isinstance(cur, int):
            continue
        try:
            setattr(g, k, cur + int(v))
        except (TypeError, ValueError):
            continue
    merge_workspace_slug(g, workspace_root)
    save_global_summary(g)


def mirror_bump_usage_counts_global(
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
    g = load_global_summary()
    if h:
        g.harness_counts[h] = g.harness_counts.get(h, 0) + 1
    for key in hm_keys:
        g.harness_model_counts[key] = g.harness_model_counts.get(key, 0) + 1
    merge_workspace_slug(g, workspace_root)
    save_global_summary(g)


def add_completion_rollups_global(
    workspace_root: Path,
    *,
    duration_sec: float,
    token_delta: int,
    lines_added: int,
    lines_deleted: int,
) -> None:
    g = load_global_summary()
    g.total_task_wall_seconds += max(0.0, float(duration_sec))
    g.total_tokens += max(0, int(token_delta))
    g.lines_added += max(0, int(lines_added))
    g.lines_deleted += max(0, int(lines_deleted))
    merge_workspace_slug(g, workspace_root)
    save_global_summary(g)


__all__ = [
    "add_completion_rollups_global",
    "global_analytics_dir",
    "global_summary_path",
    "load_global_summary",
    "merge_workspace_slug",
    "mirror_bump_global",
    "mirror_bump_usage_counts_global",
    "save_global_summary",
]
