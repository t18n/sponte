"""Run external programs with list argv only (no shell)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import IO


def run_checked(
    argv: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    stdout: int | IO | None = subprocess.PIPE,
    stderr: int | IO | None = subprocess.PIPE,
    stdin: int | IO | None = None,
) -> subprocess.CompletedProcess[str]:
    if not argv:
        raise ValueError("argv must be non-empty")
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        text=True,
        check=False,
        shell=False,
    )
