"""Rich-based progress output."""

from __future__ import annotations

from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from rich.console import Console

_console: Console | None = None


def get_console(stderr: bool = True) -> Console:
    global _console
    from rich.console import Console

    if _console is None:
        _console = Console(stderr=stderr)
    return _console


def max_agent_steps(
    implement_max: int,
    holistic_passes: int,
    conflict_max: int,
    *,
    consistency_enabled: bool,
    consistency_implement_max: int,
) -> int:
    """Upper bound for phase-bar steps: PLAN + IMPLEMENT + optional consistency + holistic + WRAP + VERIFY + conflicts."""
    cim = max(1, consistency_implement_max)
    consistency_block = (1 + cim) if consistency_enabled else 0
    hp = max(1, holistic_passes)
    return 1 + implement_max + consistency_block + 2 * hp + 1 + 1 + conflict_max


def banner(msg: str, *, err: TextIO | None = None) -> None:
    from rich.panel import Panel

    c = get_console(stderr=err is None)
    c.print(Panel.fit(msg, title="ralph", border_style="cyan"))


def cycle_line(
    current: int,
    max_cycles: int | None,
    remaining_sec: float | None,
    *,
    generation_id: str | None = None,
) -> None:
    c = get_console()
    gen = f" · session [cyan]{generation_id}[/cyan]" if generation_id else ""
    if max_cycles is not None:
        c.print(f"[bold][ralph][/bold] Cycle {current} of {max_cycles}{gen}")
    else:
        c.print(f"[bold][ralph][/bold] Cycle {current} (no cycle cap){gen}")
    if remaining_sec is not None and remaining_sec >= 0:
        m, s = divmod(int(remaining_sec), 60)
        h, m = divmod(m, 60)
        c.print(f"[dim]Session time remaining ~ {h}h {m}m {s}s[/dim]")


def task_block(rel: str, label: str, open_c: int, done_c: int) -> None:
    c = get_console()
    c.print(f"[ralph] Task: [green]{rel}[/green]")
    c.print(f"[ralph] Title: {label}")
    c.print(f"[ralph] Checklist: {open_c} open, {done_c} done")


def _format_token_total(token_total: int | None, *, estimated: bool = False) -> str:
    if token_total is None:
        return ""
    label = "tokens~=" if estimated else "tokens="
    return f" {label}{token_total:,}"


def format_phase_bar_line(
    cur: int,
    max_s: int,
    label: str,
    *,
    model: str | None = None,
    token_total: int | None = None,
    token_estimated: bool = False,
) -> str:
    width = 20
    pct = min(100, cur * 100 // max(max_s, 1))
    filled = min(width, cur * width // max(max_s, 1))
    bar = "█" * filled + "░" * (width - filled)
    model_text = f" model={model}" if model else ""
    return f"[ralph] Phase [{bar}] {cur}/{max_s}  {label}{model_text}{_format_token_total(token_total, estimated=token_estimated)}"


def phase_bar(
    cur: int,
    max_s: int,
    label: str,
    *,
    model: str | None = None,
    token_total: int | None = None,
    token_estimated: bool = False,
) -> None:
    c = get_console()
    c.print(
        format_phase_bar_line(
            cur,
            max_s,
            label,
            model=model,
            token_total=token_total,
            token_estimated=token_estimated,
        )
    )


def format_step_done_line(
    label: str,
    summary: str,
    *,
    model: str | None = None,
    token_total: int | None = None,
    token_estimated: bool = False,
) -> str:
    model_text = f" model={model}" if model else ""
    return f"[green][ralph] Done:[/green] {label}{model_text}{_format_token_total(token_total, estimated=token_estimated)} — {summary}"


def step_done(
    label: str,
    summary: str,
    *,
    model: str | None = None,
    token_total: int | None = None,
    token_estimated: bool = False,
) -> None:
    c = get_console()
    c.print(
        format_step_done_line(
            label,
            summary,
            model=model,
            token_total=token_total,
            token_estimated=token_estimated,
        )
    )


def merge_precheck_warning(reason: str, detail: str = "", *, max_detail_lines: int = 15) -> None:
    """User-visible notice that primary is not clean before merge (run log should also record details)."""
    c = get_console()
    c.print(f"[yellow][ralph] Merge precheck:[/yellow] {reason}")
    if not detail.strip():
        return
    lines = detail.strip().splitlines()
    if len(lines) > max_detail_lines:
        rest = len(lines) - max_detail_lines
        lines = lines[:max_detail_lines] + [f"... ({rest} more line{'s' if rest != 1 else ''})"]
    for ln in lines:
        c.print(f"[dim]  {ln}[/dim]")


def merge_precheck_failed(reason: str, detail: str = "", *, max_detail_lines: int = 15) -> None:
    """User-visible explanation when merge cannot start (run log should also record details)."""
    c = get_console()
    c.print(f"[red][ralph] Merge precheck failed:[/red] {reason}")
    if not detail.strip():
        return
    lines = detail.strip().splitlines()
    if len(lines) > max_detail_lines:
        rest = len(lines) - max_detail_lines
        lines = lines[:max_detail_lines] + [f"... ({rest} more line{'s' if rest != 1 else ''})"]
    for ln in lines:
        c.print(f"[dim]  {ln}[/dim]")
