"""Parse human durations into seconds."""

from __future__ import annotations

import re

_DURATION_RE = re.compile(
    r"^\s*(\d+)\s*([hms]?)\s*$",
    re.IGNORECASE,
)


def parse_duration_to_seconds(text: str) -> int:
    """Parse '3600', '6h', '90m', '1h30m' (combined) into seconds."""
    t = text.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("empty duration")
    if t.isdigit():
        return int(t)
    total = 0
    for m in re.finditer(r"(\d+)([hms])", t):
        n, u = int(m.group(1)), m.group(2)
        if u == "h":
            total += n * 3600
        elif u == "m":
            total += n * 60
        else:
            total += n
    if total <= 0:
        raise ValueError("duration must be positive (use e.g. 6h, 90m, or raw seconds)")
    return total


def format_seconds_human(total_sec: int) -> str:
    """Human-readable duration (e.g. 21600 -> '6h', 90 -> '1m 30s')."""
    if total_sec <= 0:
        return "0s"
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    bits: list[str] = []
    if h:
        bits.append(f"{h}h")
    if m:
        bits.append(f"{m}m")
    if s or not bits:
        bits.append(f"{s}s")
    return " ".join(bits)
