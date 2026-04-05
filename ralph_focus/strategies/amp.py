"""Amp CLI backend (ampcode.com) — headless execute mode (`amp -x`)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


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
    ) -> tuple[int, dict[str, int]]:
        del use_stream_json, metrics_out
        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"\n======== {iso} amp model={model or 'default'} ========\n"
        _append_log(log_file, header)
        bin_path = _amp_bin()
        args: list[str] = [bin_path]
        if _dangerously_allow_all():
            args.append("--dangerously-allow-all")
        args.extend(["-x", prompt])
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
