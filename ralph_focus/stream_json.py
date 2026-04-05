"""Parse cursor-agent stream-json captures for summaries and token totals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _collect_usage_bits(obj: Any, out: list[str], seen: set[int]) -> None:
    if not isinstance(obj, dict):
        return
    oid = id(obj)
    if oid in seen:
        return
    seen.add(oid)

    usage = obj.get("usage") or obj.get("tokenUsage") or obj.get("token_usage")
    if isinstance(usage, dict):
        pairs: list[tuple[str, Any]] = []
        for k, v in usage.items():
            if v is None:
                continue
            lk = k.lower()
            if "token" in lk or lk in ("input", "output", "prompt", "completion", "cache"):
                pairs.append((k, v))
        if pairs:
            for k, v in sorted(pairs, key=lambda x: x[0]):
                out.append(f"{k}={v}")
        return

    for v in obj.values():
        if isinstance(v, dict):
            _collect_usage_bits(v, out, seen)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _collect_usage_bits(item, out, seen)


def last_result_from_stream_path(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return None
    last: dict[str, Any] | None = None
    last_completion: dict[str, Any] | None = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(o, dict):
            continue
        if o.get("type") == "result":
            last = o
        elif o.get("type") == "completion":
            last_completion = o
    if last is None and last_completion is not None:
        last = last_completion
    if last is None:
        try:
            o = json.loads(raw)
            if isinstance(o, dict):
                if o.get("type") in ("result", "completion"):
                    last = o
                elif any(
                    k in o
                    for k in ("usage", "tokenUsage", "duration_ms", "durationMs")
                ):
                    last = o
        except json.JSONDecodeError:
            pass
    return last


def summarize_result(o: dict[str, Any]) -> str:
    bits: list[str] = []
    if "duration_ms" in o and o["duration_ms"] is not None:
        bits.append(f"duration_ms={o['duration_ms']}")
    elif "durationMs" in o and o["durationMs"] is not None:
        bits.append(f"durationMs={o['durationMs']}")
    if "subtype" in o and o["subtype"] is not None:
        bits.append(f"subtype={o['subtype']}")

    usage_bits: list[str] = []
    _collect_usage_bits(o, usage_bits, set())
    if usage_bits:
        bits.append("tokens: " + ", ".join(usage_bits[:12]))
        if len(usage_bits) > 12:
            bits.append(f"(+{len(usage_bits) - 12} more)")

    for k in ("cost_usd", "costUSD", "cost"):
        if k in o and o[k] is not None:
            bits.append(f"{k}={o[k]}")
            break

    return "; ".join(bits)


def parse_usage_totals(path: Path) -> dict[str, int]:
    r = last_result_from_stream_path(path)
    if not r:
        return {}
    usage = r.get("usage") or r.get("tokenUsage") or r.get("token_usage")
    if isinstance(usage, dict):
        return {str(k): int(v) for k, v in usage.items() if isinstance(v, (int, float))}
    return {}


def summarize_stream_file(path: Path) -> str:
    r = last_result_from_stream_path(path)
    if not r:
        return ""
    return summarize_result(r)
