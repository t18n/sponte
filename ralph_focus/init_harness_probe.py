"""Validate harness + model selection during ``sponte init`` (best-effort)."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

from ralph_focus.contracts import RunRequest, get_harness
from ralph_focus.workspace_settings import CustomHarnessConfig

_INIT_PROBE_PROMPT = 'Reply with exactly the single word OK and nothing else.'


def probe_init_harness_selection(
    primary: Path,
    *,
    harness_id: str,
    plan_model: str,
    execute_model: str,
    custom: CustomHarnessConfig | None,
    status: Callable[[str], None] | None = None,
) -> str | None:
    """
    Return an error message if validation fails, else ``None``.

    Set ``SPONTE_INIT_SKIP_HARNESS_PROBE=1`` to skip (tests / offline).
    *status* is invoked with short human-readable progress lines (TTY feedback).
    """
    if os.environ.get("SPONTE_INIT_SKIP_HARNESS_PROBE", "").lower() in ("1", "true", "yes"):
        return None
    hid = harness_id.strip().lower()
    if hid == "custom":
        return _probe_custom_harness(primary, custom, status=status)
    return _probe_builtin_harness(
        primary, hid, plan_model.strip(), execute_model.strip(), status=status
    )


def _probe_custom_harness(
    primary: Path,
    custom: CustomHarnessConfig | None,
    *,
    status: Callable[[str], None] | None,
) -> str | None:
    if custom is None or not custom.executable.strip():
        return "custom harness needs an executable name"
    if custom.probe:
        if status:
            status("Running custom harness probe command…")
        cmd = list(custom.probe)
        try:
            proc = subprocess.run(
                cmd,
                cwd=primary,
                capture_output=True,
                text=True,
                timeout=120,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return "custom harness probe timed out (120s)"
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[:240]
            return f"custom probe failed (exit {proc.returncode}): {tail}" if tail else "custom probe failed"
        return None
    if status:
        status("Checking custom harness executable on PATH…")
    if not shutil.which(custom.executable.strip()):
        return f"executable not on PATH: {custom.executable.strip()}"
    return None


def _probe_builtin_harness(
    primary: Path,
    harness_id: str,
    plan_model: str,
    execute_model: str,
    *,
    status: Callable[[str], None] | None,
) -> str | None:
    if status:
        status("Checking harness and CLI availability…")
    try:
        harness = get_harness(harness_id)
    except ValueError as exc:
        return str(exc)
    rep = harness.availability()
    if not rep.available:
        return "; ".join(rep.problems) if rep.problems else "harness unavailable"
    log_dir = primary / ".sponte" / ".probe-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    for label, model in (("plan_model", plan_model), ("execute_model", execute_model)):
        if status:
            human = "plan model" if label == "plan_model" else "execute model"
            status(f"Verifying {human} with a short probe (up to 2 minutes)…")
        logf = log_dir / f"init-probe-{label}.log"
        req = harness.prepare(
            RunRequest(
                cwd=primary,
                model=model,
                prompt=_INIT_PROBE_PROMPT,
                log_file=logf,
                use_stream_json=False,
                tee_output=False,
                metrics_out=None,
            )
        )

        def run_once():
            return harness.run(req)

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(run_once)
                result = fut.result(timeout=120)
        except FuturesTimeout:
            return f"{label}: probe timed out (120s; model may be invalid or network stuck)"
        if result.exit_code != 0:
            return f"{label}: harness exited {result.exit_code} (check model name for this harness)"
    return None
