"""Known workspace roots in Sponte app state (cross-workspace registry)."""

from __future__ import annotations

import json
from pathlib import Path

from ralph_focus.app_state_paths import sponte_state_base_dir

REGISTRY_FILENAME = "known_workspaces.json"
_MAX_ENTRIES = 64


def registry_path() -> Path:
    return sponte_state_base_dir() / REGISTRY_FILENAME


def load_known_workspaces() -> list[Path]:
    path = registry_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, dict):
        return []
    paths = raw.get("paths")
    if not isinstance(paths, list):
        return []
    out: list[Path] = []
    for item in paths:
        if isinstance(item, str) and item.strip():
            p = Path(item).expanduser()
            try:
                out.append(p.resolve())
            except OSError:
                continue
    # de-dupe preserving order
    seen: set[str] = set()
    unique: list[Path] = []
    for p in out:
        key = p.as_posix()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def register_workspace(root: Path) -> None:
    resolved = root.resolve()
    current = load_known_workspaces()
    if resolved in current:
        ordered = [resolved, *[p for p in current if p != resolved]]
    else:
        ordered = [resolved, *current]
    save_known_workspaces(ordered[:_MAX_ENTRIES])


def save_known_workspaces(paths: list[Path]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"paths": [str(p.resolve()) for p in paths[:_MAX_ENTRIES]]}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "load_known_workspaces",
    "register_workspace",
    "registry_path",
    "save_known_workspaces",
]
