"""Warp Oz CLI backend (`oz agent run`, headless-friendly with WARP_API_KEY)."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ralph_focus.live_usage import with_live_usage_events
from ralph_focus.stream_runtime import run_subprocess_streaming

if TYPE_CHECKING:
    from ralph_focus.contracts import RunEventCallback, RunResult, RunWatchdog

def _oz_bin() -> str:
    return os.environ.get("RALPH_OZ_BIN", "oz")


def _append_log(log_file: Path, chunk: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(chunk)


class OzStrategy:
    id = "oz"

    def __init__(self) -> None:
        self._bin = _oz_bin()

    def check_available(self) -> list[str]:
        if shutil.which(self._bin):
            return []
        return [f"{self._bin!r} not found on PATH (set RALPH_OZ_BIN)"]

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

        del use_stream_json, metrics_out
        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"\n======== {iso} oz agent run model={model or 'default'} ========\n"
        _append_log(log_file, header)
        args: list[str] = [
            self._bin,
            "agent",
            "run",
            "-C",
            str(cwd),
            "--prompt",
            prompt,
        ]
        if model and model.strip().lower() != "auto":
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
