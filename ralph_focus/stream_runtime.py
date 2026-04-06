"""Shared subprocess streaming helpers for harness strategies."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ralph_focus.run_events import RunEvent, RunEventCallback, RunWatchdog


def _append_log(log_file: Path, chunk: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(chunk)


@dataclass(frozen=True)
class StreamingRunResult:
    exit_code: int
    output: str
    retryable: bool = False
    cancellation_reason: str = ""


def _emit(event_callback: RunEventCallback | None, event: RunEvent) -> None:
    if event_callback is None:
        return
    event_callback(event)


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1.0)


def run_subprocess_streaming(
    args: list[str],
    *,
    cwd: Path,
    log_file: Path,
    tee: bool,
    watchdog: RunWatchdog | None,
    event_callback: RunEventCallback | None = None,
    env: dict[str, str] | None = None,
) -> StreamingRunResult:
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None

    lines: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()

    started = time.monotonic()
    last_stream = started
    output_parts: list[str] = []
    cancellation_reason = ""
    retryable = False

    while True:
        try:
            item = lines.get(timeout=0.05)
        except queue.Empty:
            now = time.monotonic()
            if watchdog and watchdog.total_runtime_timeout_sec is not None:
                if now - started > watchdog.total_runtime_timeout_sec:
                    cancellation_reason = "total_runtime_timeout"
            if not cancellation_reason and watchdog and watchdog.stall_timeout_sec is not None:
                if now - last_stream > watchdog.stall_timeout_sec:
                    cancellation_reason = "stall_timeout"
            if cancellation_reason:
                retryable = True
                marker = f"sponte watchdog: cancelled run ({cancellation_reason})\n"
                _append_log(log_file, marker)
                _emit(event_callback, RunEvent(kind="watchdog", reason=cancellation_reason, text=marker.strip()))
                _terminate_process(proc)
                break
            if proc.poll() is not None and lines.empty():
                break
            continue

        if item is None:
            break

        output_parts.append(item)
        last_stream = time.monotonic()
        if tee:
            sys.stdout.write(item)
        _append_log(log_file, item)
        _emit(event_callback, RunEvent(kind="output", text=item))
        _emit(event_callback, RunEvent(kind="heartbeat", text=item))

    thread.join(timeout=1.0)
    rc = proc.returncode or 0
    if cancellation_reason:
        rc = 1
    return StreamingRunResult(
        exit_code=rc,
        output="".join(output_parts),
        retryable=retryable,
        cancellation_reason=cancellation_reason,
    )
