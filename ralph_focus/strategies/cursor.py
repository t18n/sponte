"""Cursor `cursor-agent` backend."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ralph_focus.stream_json import parse_usage_totals, summarize_stream_file


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
    ) -> tuple[int, dict[str, int]]:
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
            if tee and use_stream_json:
                proc = subprocess.Popen(
                    args,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                lines: list[str] = []
                for line in proc.stdout:
                    lines.append(line)
                    sys.stdout.write(line)
                    _append_log(log_file, line)
                proc.wait()
                cap_path.write_text("".join(lines), encoding="utf-8")
                rc = proc.returncode or 0
            else:
                proc = subprocess.run(
                    args,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                _append_log(log_file, out)
                if use_stream_json:
                    cap_path.write_text(out, encoding="utf-8")
                rc = proc.returncode or 0
            if use_stream_json and cap_path.is_file():
                usage = parse_usage_totals(cap_path)
        finally:
            if use_stream_json and metrics_out and cap_path.is_file():
                summary = summarize_stream_file(cap_path)
                if summary:
                    metrics_out.write_text(summary, encoding="utf-8")
            cap_path.unlink(missing_ok=True)
        return rc, usage
