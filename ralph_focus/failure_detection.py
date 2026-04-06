"""Classify transient agent failures and gutter/no-progress loops."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from config.defaults import NO_PROGRESS_LOOPS_MAX


class FailureKind(str, Enum):
    TRANSIENT = "transient"
    GUTTER = "gutter"
    FATAL = "fatal"


@dataclass(frozen=True)
class ProgressSnapshot:
    pending_count: int
    dirty: bool
    head: str


@dataclass(frozen=True)
class FailureClassification:
    kind: FailureKind
    detail: str


_TRANSIENT_PATTERNS = (
    re.compile(r"\b429\b"),
    re.compile(r"rate limit", re.I),
    re.compile(r"timed? out", re.I),
    re.compile(r"watchdog", re.I),
    re.compile(r"stall[_ ]timeout", re.I),
    re.compile(r"total[_ ]runtime[_ ]timeout", re.I),
    re.compile(r"cancelled run", re.I),
    re.compile(r"temporar", re.I),
    re.compile(r"no space left on device", re.I),
    re.compile(r"connection reset", re.I),
    re.compile(r"econnreset", re.I),
    re.compile(r"unavailable", re.I),
    re.compile(r"overloaded", re.I),
)


def classify_agent_failure(
    summary: str,
    detail: str,
    *,
    no_progress_streak: int,
    before: ProgressSnapshot | None = None,
    after: ProgressSnapshot | None = None,
) -> FailureClassification:
    combined = "\n".join(part for part in (summary, detail) if part).strip()
    for pattern in _TRANSIENT_PATTERNS:
        if pattern.search(combined):
            return FailureClassification(FailureKind.TRANSIENT, combined or "transient agent failure")

    if (
        no_progress_streak >= NO_PROGRESS_LOOPS_MAX
        and before is not None
        and after is not None
        and before.pending_count == after.pending_count
        and before.dirty == after.dirty
        and before.head == after.head
    ):
        return FailureClassification(
            FailureKind.GUTTER,
            "Repeated no-progress loop detected; agent state appears stuck.",
        )

    return FailureClassification(FailureKind.FATAL, combined or "agent step failed")
