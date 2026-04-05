"""Shared small interactive helpers."""

from __future__ import annotations

def resolve_choice_index(*, choice_count: int, raw_index: int) -> int:
    if raw_index < 1 or raw_index > choice_count:
        raise ValueError(f"choice index {raw_index} out of range 1..{choice_count}")
    return raw_index - 1
