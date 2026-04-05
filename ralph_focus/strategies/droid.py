"""Factory.ai Droid CLI backend (`droid exec` headless)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config.defaults import DROID_AUTO_LEVEL, DROID_EXECUTABLE
from ralph_focus.stream_json import parse_usage_totals, summarize_stream_file


def _append_log(log_file: Path, chunk: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(chunk)


class DroidStrategy:
    id = "droid"

    def __init__(self) -> None:
        self._bin = DROID_EXECUTABLE
        self._auto = DROID_AUTO_LEVEL

    def check_available(self) -> list[str]:
        errs: list[str] = []
        if self._auto not in ("low", "medium", "high"):
            errs.append(
                f"invalid RALPH_DROID_AUTO={self._auto!r} (use low|medium|high)",
            )
        if not shutil.which(self._bin):
            errs.append(f"{self._bin!r} not found on PATH (set RALPH_DROID_BIN)")
        if not os.environ.get("FACTORY_API_KEY", "").strip():
            errs.append("FACTORY_API_KEY is not set (Factory CLI auth)")
        return errs

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
        header = (
            f"\n======== {iso} droid exec model={model or 'default'} "
            f"auto={self._auto} {fmt} ========\n"
        )
        _append_log(log_file, header)

        fd, prompt_path_str = tempfile.mkstemp(suffix=".md", prefix="ralph-droid-prompt-")
        os.close(fd)
        prompt_path = Path(prompt_path_str)
        prompt_path.write_text(prompt, encoding="utf-8")

        fd2, cap_name = tempfile.mkstemp(suffix=".ndjson", prefix="ralph-droid-")
        os.close(fd2)
        cap_path = Path(cap_name)
        usage: dict[str, int] = {}
        try:
            args: list[str] = [
                self._bin,
                "exec",
                "--cwd",
                str(cwd),
                "--auto",
                self._auto,
                "-f",
                str(prompt_path),
            ]
            if model and model.strip().lower() != "auto":
                args.extend(["-m", model])
            if use_stream_json:
                args.extend(["--output-format", "stream-json"])

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
            prompt_path.unlink(missing_ok=True)
            if use_stream_json and metrics_out and cap_path.is_file():
                summary = summarize_stream_file(cap_path)
                if summary:
                    metrics_out.write_text(summary, encoding="utf-8")
            cap_path.unlink(missing_ok=True)
        return rc, usage
