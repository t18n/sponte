"""User-defined headless CLI harness from ``.sponte/settings.json``."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ralph_focus.live_usage import with_live_usage_events
from ralph_focus.stream_runtime import run_subprocess_streaming
from ralph_focus.workspace_settings import CustomHarnessConfig

if TYPE_CHECKING:
    from ralph_focus.contracts import RunEventCallback, RunResult, RunWatchdog


def _append_log(log_file: Path, chunk: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(chunk)


def _executable_resolves(executable: str) -> bool:
    exe = executable.strip()
    if not exe:
        return False
    p = Path(exe)
    if p.is_file():
        return os.access(p, os.X_OK)
    return shutil.which(exe) is not None


class CustomCLIStrategy:
    """Thin wrapper: ``executable`` + fixed ``args`` + prompt as final argument."""

    id = "custom"

    def __init__(self, cfg: CustomHarnessConfig) -> None:
        self._cfg = cfg

    def check_available(self) -> list[str]:
        exe = self._cfg.executable.strip()
        if not exe:
            return ["custom harness: missing executable in settings"]
        if not _executable_resolves(exe):
            return [f"custom harness: executable not found or not runnable: {exe!r}"]
        return []

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
        header = f"\n======== {iso} custom harness model={model!r} ========\n"
        _append_log(log_file, header)
        env = os.environ.copy()
        env["SPONTE_MODEL"] = model
        cmd = [self._cfg.executable.strip(), *self._cfg.args, prompt]
        live_event_callback = with_live_usage_events(
            use_stream_json=False,
            event_callback=event_callback,
        )
        result = run_subprocess_streaming(
            cmd,
            cwd=cwd,
            env=env,
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
