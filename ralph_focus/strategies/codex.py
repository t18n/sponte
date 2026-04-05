"""OpenAI Codex CLI backend (`codex` binary; flags vary by version)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.defaults import CODEX_EXECUTABLE


def _append_log(log_file: Path, chunk: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(chunk)


class CodexStrategy:
    id = "codex"

    def __init__(self) -> None:
        self._bin = CODEX_EXECUTABLE

    def check_available(self) -> list[str]:
        if shutil.which(self._bin):
            return []
        return [f"{self._bin!r} not found on PATH (set RALPH_CODEX_BIN)"]

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
        del use_stream_json, metrics_out
        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"\n======== {iso} codex model={model or 'default'} ========\n"
        _append_log(log_file, header)
        # Common pattern: `codex exec "<prompt>"` — adjust if your installed CLI differs.
        args: list[str] = [self._bin, "exec", prompt]
        if model:
            args = [self._bin, "exec", "--model", model, prompt]
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
