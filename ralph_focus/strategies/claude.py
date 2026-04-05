"""Claude Code CLI backend."""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


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
    ) -> tuple[int, dict[str, int]]:
        del use_stream_json, metrics_out  # Claude has no stream-json metrics yet
        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"\n======== {iso} claude model={model or 'default'} ========\n"
        _append_log(log_file, header)
        args = ["claude", "-p", prompt]
        if model:
            args.extend(["--model", model])
        if tee:
            proc = subprocess.Popen(
                args,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                _append_log(log_file, line)
            proc.wait()
            return proc.returncode or 0, {}
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        out = (proc.stdout or "") + (proc.stderr or "")
        _append_log(log_file, out)
        return proc.returncode or 0, {}
