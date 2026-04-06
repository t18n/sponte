"""Cursor `cursor-agent` backend."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ralph_focus.live_usage import with_live_usage_events
from ralph_focus.stream_json import parse_usage_totals, summarize_stream_file
from ralph_focus.stream_runtime import run_subprocess_streaming

if TYPE_CHECKING:
    from ralph_focus.contracts import RunEventCallback, RunResult, RunWatchdog


def _append_log(log_file: Path, chunk: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(chunk)


class CursorStrategy:
    id = "cursor"

    def check_available(self) -> list[str]:
        if shutil.which("cursor-agent"):
            return []
        return ["cursor-agent not found on PATH"]

    def run(
        self,
        cwd: Path,
        model: str,
        prompt: str,
        log_file: Path,
        *,
        use_stream_json: bool,
        tee: bool,
        metrics_out: Path | None,
        watchdog: "RunWatchdog | None",
        event_callback: "RunEventCallback | None",
    ) -> "RunResult":
        from ralph_focus.contracts import RunResult

        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fmt = "stream-json" if use_stream_json else "text"
        header = f"\n======== {iso} cursor-agent model={model} {fmt} ========\n"
        _append_log(log_file, header)
        args = [
            "cursor-agent",
            "-p",
            "--force",
            "--output-format",
            fmt,
            "--model",
            model,
            prompt,
        ]
        fd, cap_name = tempfile.mkstemp(suffix=".ndjson", prefix="ralph-cursor-")
        os.close(fd)
        cap_path = Path(cap_name)
        usage: dict[str, int] = {}
        try:
            live_event_callback = with_live_usage_events(
                use_stream_json=use_stream_json,
                event_callback=event_callback,
            )
            result = run_subprocess_streaming(
                args,
                cwd=cwd,
                log_file=log_file,
                tee=tee and use_stream_json,
                watchdog=watchdog,
                event_callback=live_event_callback,
            )
            if use_stream_json:
                cap_path.write_text(result.output, encoding="utf-8")
            if use_stream_json and cap_path.is_file():
                usage = parse_usage_totals(cap_path)
        finally:
            if use_stream_json and metrics_out and cap_path.is_file():
                summary = summarize_stream_file(cap_path)
                if summary:
                    metrics_out.write_text(summary, encoding="utf-8")
            cap_path.unlink(missing_ok=True)
        return RunResult(
            exit_code=result.exit_code,
            usage=usage,
            retryable=result.retryable,
            cancellation_reason=result.cancellation_reason,
        )
