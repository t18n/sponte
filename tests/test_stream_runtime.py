from __future__ import annotations

import sys
from pathlib import Path

from ralph_focus.contracts import RunEvent, RunWatchdog


def test_run_subprocess_streams_output_and_events(tmp_path: Path) -> None:
    from ralph_focus.stream_runtime import run_subprocess_streaming

    logf = tmp_path / "run.log"
    seen: list[RunEvent] = []

    result = run_subprocess_streaming(
        [sys.executable, "-u", "-c", "print('one'); print('two')"],
        cwd=tmp_path,
        log_file=logf,
        tee=False,
        watchdog=RunWatchdog(stall_timeout_sec=1.0, total_runtime_timeout_sec=5.0),
        event_callback=seen.append,
    )

    assert result.exit_code == 0
    assert result.cancellation_reason == ""
    assert result.output == "one\ntwo\n"
    assert [event.kind for event in seen] == ["output", "heartbeat", "output", "heartbeat"]
    assert "one\ntwo\n" in logf.read_text(encoding="utf-8")


def test_run_subprocess_cancels_when_stream_stalls(tmp_path: Path) -> None:
    from ralph_focus.stream_runtime import run_subprocess_streaming

    logf = tmp_path / "stall.log"

    result = run_subprocess_streaming(
        [sys.executable, "-u", "-c", "import time; print('start'); time.sleep(5)"],
        cwd=tmp_path,
        log_file=logf,
        tee=False,
        watchdog=RunWatchdog(stall_timeout_sec=0.2, total_runtime_timeout_sec=5.0),
    )

    assert result.exit_code == 1
    assert result.retryable is True
    assert result.cancellation_reason == "stall_timeout"
    assert "start\n" in result.output
    assert "start\n" in logf.read_text(encoding="utf-8")


def test_run_subprocess_cancels_when_total_runtime_expires(tmp_path: Path) -> None:
    from ralph_focus.stream_runtime import run_subprocess_streaming

    logf = tmp_path / "runtime.log"

    result = run_subprocess_streaming(
        [
            sys.executable,
            "-u",
            "-c",
            "import time\nfor i in range(100):\n print(i)\n time.sleep(0.05)",
        ],
        cwd=tmp_path,
        log_file=logf,
        tee=False,
        watchdog=RunWatchdog(stall_timeout_sec=1.0, total_runtime_timeout_sec=0.2),
    )

    assert result.exit_code == 1
    assert result.retryable is True
    assert result.cancellation_reason == "total_runtime_timeout"
    assert result.output
    assert logf.read_text(encoding="utf-8")
