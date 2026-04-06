"""Claude Code CLI backend."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ralph_focus.live_usage import with_live_usage_events
from ralph_focus.stream_runtime import run_subprocess_streaming

if TYPE_CHECKING:
    from ralph_focus.contracts import RunEventCallback, RunResult, RunWatchdog

def _append_log(log_file: Path, chunk: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(chunk)


class ClaudeStrategy:
    id = "claude"

    def check_available(self) -> list[str]:
        if shutil.which("claude"):
            return []
        return ["claude CLI not found on PATH"]

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

        del use_stream_json, metrics_out  # Claude has no stream-json metrics yet
        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"\n======== {iso} claude model={model or 'default'} ========\n"
        _append_log(log_file, header)
        args = ["claude", "-p", prompt]
        if model:
            args.extend(["--model", model])
        live_event_callback = with_live_usage_events(
            use_stream_json=False,
            event_callback=event_callback,
        )
        result = run_subprocess_streaming(
            args,
            cwd=cwd,
            log_file=log_file,
            tee=tee,
            watchdog=watchdog,
            event_callback=live_event_callback,
        )
        return RunResult(
            exit_code=result.exit_code,
            usage={},
            retryable=result.retryable,
            cancellation_reason=result.cancellation_reason,
        )
