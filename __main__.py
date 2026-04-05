"""Allow `python .` from a local Sponte checkout."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    try:
        from ralph_focus.cli import main
    except ImportError as exc:
        if "typer" in str(exc).lower() or "rich" in str(exc).lower():
            sys.stderr.write("Dependencies missing. Run `uv sync`, then `uv run sponte ...`.\n")
            raise SystemExit(1) from exc
        raise
    main()
