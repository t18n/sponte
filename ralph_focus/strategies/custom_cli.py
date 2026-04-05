"""User-defined headless CLI harness from ``.sponte/settings.json``."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ralph_focus.workspace_settings import CustomHarnessConfig


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
    ) -> tuple[int, dict[str, int]]:
        del use_stream_json, tee, metrics_out
        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"\n======== {iso} custom harness model={model!r} ========\n"
        _append_log(log_file, header)
        env = os.environ.copy()
        env["SPONTE_MODEL"] = model
        cmd = [self._cfg.executable.strip(), *self._cfg.args, prompt]
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=86_400,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            _append_log(log_file, "custom harness: subprocess timed out (24h)\n")
            return 1, {}
        out = (proc.stdout or "") + (proc.stderr or "")
        if out:
            _append_log(log_file, out)
            if not out.endswith("\n"):
                _append_log(log_file, "\n")
        return proc.returncode or 0, {}
