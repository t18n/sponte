"""Amp CLI backend (ampcode.com) — headless execute mode (`amp -x`)."""

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

def _append_log(log_file: Path, chunk: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(chunk)


def _amp_bin() -> str:
    return os.environ.get("RALPH_AMP_BIN", "amp").strip() or "amp"


def _dangerously_allow_all() -> bool:
    v = os.environ.get("RALPH_AMP_DANGEROUSLY_ALLOW_ALL", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


class AmpStrategy:
    id = "amp"

    def check_available(self) -> list[str]:
        b = _amp_bin()
        if shutil.which(b):
            return []
        return [f"{b!r} not found on PATH (set RALPH_AMP_BIN)"]

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
        header = f"\n======== {iso} amp model={model or 'default'} ========\n"
        _append_log(log_file, header)
        bin_path = _amp_bin()
        args: list[str] = [bin_path]
        if _dangerously_allow_all():
            args.append("--dangerously-allow-all")
        args.extend(["-x", prompt])
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
