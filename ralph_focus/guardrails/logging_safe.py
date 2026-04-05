"""Optional redaction for log lines (tokens / secrets)."""

from __future__ import annotations

import re

_REDACT_KEYS = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|bearer)\s*[=:]\s*\S+",
)


def redact_line(line: str) -> str:
    return _REDACT_KEYS.sub(r"\1=<redacted>", line)
