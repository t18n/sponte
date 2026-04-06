"""Helpers for converting streamed harness output into live usage events."""

from __future__ import annotations

import math

from ralph_focus.run_events import RunEvent, RunEventCallback
from ralph_focus.stream_json import usage_delta_from_stream_line


def _estimate_text_usage(text: str) -> dict[str, int]:
    stripped = text.strip()
    if not stripped:
        return {}
    return {"output_tokens": max(1, math.ceil(len(stripped) / 4))}


def with_live_usage_events(
    *,
    use_stream_json: bool,
    event_callback: RunEventCallback | None,
) -> RunEventCallback | None:
    if event_callback is None:
        return None

    previous_usage: dict[str, int] = {}

    def _wrapped(event: RunEvent) -> None:
        nonlocal previous_usage
        if event.kind == "output":
            if use_stream_json:
                delta, previous_usage = usage_delta_from_stream_line(event.text, previous_usage)
                if delta:
                    event_callback(RunEvent(kind="usage", text=event.text, usage_delta=delta, estimated=False))
            else:
                delta = _estimate_text_usage(event.text)
                if delta:
                    event_callback(RunEvent(kind="usage", text=event.text, usage_delta=delta, estimated=True))
        event_callback(event)

    return _wrapped
