"""Typer CLI for the installed `sponte` command."""

from __future__ import annotations

import os
import re
import secrets
import sys
import shlex
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from config.defaults import (
    DEFAULT_AGENT,
    DEFAULT_EXECUTE_MODEL,
    DEFAULT_PLAN_MODEL,
    DEFAULT_PROGRESS,
    MAX_RESUME_ERRORS_UNLIMITED_SESSION,
    ROTATE_THRESHOLD_TOKENS,
    ROTATE_WARN_THRESHOLD_TOKENS,
)
from config.defaults import TASKS_DIR
from ralph_focus.contracts import get_harness
from ralph_focus.cycle import AutoFocusConfig, ProgressMode, run_one_cycle
from ralph_focus.failure_detection import FailureKind
from ralph_focus.interactive_setup import resolve_choice_index
from ralph_focus.paths import rotation_handoff_file
from ralph_focus.preflight import run_preflight
from ralph_focus.progress import cycle_line
from ralph_focus.ralph_session_lock import (
    clear_ralph_lock_matching_runner,
    finalize_ralph_lock_if_session_idle,
    write_ralph_lock,
)
from ralph_focus.resume import ResumeState, clear_resume as resume_clear_state
from ralph_focus.resume import (
    load_resume,
    resolve_runner_for_worktree,
    resume_path,
)
from ralph_focus.session_stats import SessionStats
from ralph_focus.tasks import count_checklist, task_label
from ralph_focus.time_parse import format_seconds_human, parse_duration_to_seconds
from ralph_focus.token_rotation import rotation_policy_from_overrides
from ralph_focus.worktree_cli import worktree_prune_clean, worktree_remove_interactive
from ralph_focus.workspace_resolve import (
    bootstrap_workspace_with_prompt,
    resolve_git_repo_root,
    resolve_primary_workspace,
)
from ralph_focus.workspace_init import refresh_priorities_from_backlog
from ralph_focus.workspace_tasks import sponte_tasks_layout_valid

app = typer.Typer(help="Sponte — standalone task harness powered by Ralph core.", no_args_is_help=True)
console = Console(stderr=True)


def _new_rap_id() -> str:
    """RAP id — Ralph auto-focus process id (opaque, unique per invocation)."""
    return f"rap-{secrets.token_hex(4)}"


def _effective_runner_id(runner_id_opt: str | None) -> str:
    if runner_id_opt:
        return runner_id_opt
    env = os.environ.get("RALPH_RUNNER_ID")
    if env:
        return env
    return _new_rap_id()


def compute_resumed_deadline(
    *,
    stored_deadline_epoch: str,
    default_deadline_epoch: str,
    extend_duration: str,
    now_epoch: float,
) -> str:
    deadline = stored_deadline_epoch or default_deadline_epoch
    extend_s = extend_duration.strip()
    if not extend_s:
        return deadline
    extend_sec = parse_duration_to_seconds(extend_s)
    if deadline.strip():
        try:
            base = max(now_epoch, float(deadline))
        except ValueError:
            base = now_epoch
    else:
        base = now_epoch
    return str(base + extend_sec)


def _format_exception_detail(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _token_rotation_notice(*, rotate_threshold_tokens: int) -> str:
    return (
        "Token rotation threshold was detected after the completed step "
        f"(session now at or above {rotate_threshold_tokens:,} rotation tokens); "
        "resume the same generation to continue from saved state."
    )


def _rotation_handoff_markdown(
    *,
    runner_id: str,
    resume_state: ResumeState,
    stats: SessionStats,
    rotate_threshold_tokens: int,
    task_title: str,
    pending_count: int,
    done_count: int,
) -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return "\n".join(
        [
            "# Rotation handoff",
            "",
            f"- Generated: `{timestamp}`",
            f"- Resume id: `{runner_id}`",
            f"- Exit reason: `token_rotation`",
            f"- Rotation threshold is a post-step trigger, not a hard cap: `{rotate_threshold_tokens:,}`",
            f"- Rotation tokens after the completed step: `{stats.rotation_tokens():,}`",
            f"- Current phase: `{resume_state.phase or 'unknown'}`",
            f"- Task: `{task_title}`",
            f"- Checklist: `{pending_count} open, {done_count} done`",
            f"- Task file: `{resume_state.rel_task}`",
            f"- Plan file: `{resume_state.plan_rel}`",
            f"- Worktree: `{resume_state.wt_path}`",
            f"- Log: `{resume_state.logf}`",
            f"- Cycles completed this session: `{stats.cycles_completed}`",
            f"- Agent steps this session: `{stats.agent_steps}`",
            "",
            "## Next step",
            f"Resume the same generation to continue from `{resume_state.phase or 'unknown'}`:",
            "",
            "```bash",
            f"sponte auto-focus --resume {runner_id} --plan-model auto --execute-model auto",
            "```",
        ]
    )


def _write_rotation_handoff(
    *,
    primary: Path,
    runner_id: str,
    stats: SessionStats,
    rotate_threshold_tokens: int,
) -> Path | None:
    resume_state = load_resume(primary, runner_id=runner_id)
    if resume_state is None:
        return None
    wt_path = Path(resume_state.wt_path)
    task_path = wt_path / resume_state.rel_task
    pending_count, done_count = count_checklist(task_path)
    title = task_label(task_path) if task_path.is_file() else resume_state.rel_task
    content = _rotation_handoff_markdown(
        runner_id=runner_id,
        resume_state=resume_state,
        stats=stats,
        rotate_threshold_tokens=rotate_threshold_tokens,
        task_title=title,
        pending_count=pending_count,
        done_count=done_count,
    )
    path = rotation_handoff_file(primary, runner_id=runner_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")
    return path


def _print_rotation_handoff_inline(*, path: str | Path, content: str) -> None:
    console.print(f"[yellow]Rotation handoff written:[/yellow] {path}")
    console.print(Panel(content.rstrip(), title="Rotation handoff", border_style="yellow"))


def _disk_full_resume_hint(detail: str, *, runner_id: str) -> str | None:
    if "no space left on device" not in detail.lower():
        return None
    return (
        "disk appears full; free space, then resume with: "
        f"sponte auto-focus --resume {shlex.quote(runner_id)} "
        "--plan-model auto --execute-model auto"
    )


def _print_disk_full_resume_hint(detail: str, *, runner_id: str) -> None:
    hint = _disk_full_resume_hint(detail, runner_id=runner_id)
    if hint:
        console.print(f"[yellow]{hint}[/yellow]")


def _print_auto_focus_settings(
    *,
    primary: Path,
    agent: str,
    plan_model: str,
    execute_model: str,
    rotate_threshold_tokens: int,
    warn_threshold_tokens: int,
    max_cycles: int | None,
    once: bool,
    duration_sec: int | None,
    session_deadline_epoch: str,
    progress: ProgressMode,
    cleanup_on_exit: bool,
    allow_agent_pick: bool,
    task_arg: str,
    resuming: bool,
    runner_id: str,
    complete_worktree_mode: bool = False,
) -> None:
    t = Table(title="Sponte auto-focus — session settings")
    t.add_column("Setting")
    t.add_column("Value")
    t.add_row("Repository", str(primary))
    t.add_row("Agent", agent)
    t.add_row("Plan model", plan_model)
    t.add_row("Execute model", execute_model)
    t.add_row(
        "Token rotation",
        (
            "off"
            if rotate_threshold_tokens <= 0
            else f"warn {warn_threshold_tokens} / rotate {rotate_threshold_tokens}"
        ),
    )
    t.add_row("Progress", progress)
    t.add_row("Max cycles", "∞" if max_cycles is None else str(max_cycles))
    if once:
        t.add_row("Session wall-clock", "— (--once: no wall budget)")
    elif duration_sec is not None:
        t.add_row(
            "Session wall-clock",
            f"{format_seconds_human(duration_sec)} ({duration_sec}s)",
        )
    else:
        t.add_row("Session wall-clock", "unlimited")
    if session_deadline_epoch:
        try:
            end = float(session_deadline_epoch)
            dt = datetime.fromtimestamp(end, tz=timezone.utc)
            t.add_row("Session ends (UTC)", dt.strftime("%Y-%m-%d %H:%M:%S"))
        except ValueError:
            t.add_row("Session ends (UTC)", session_deadline_epoch)
    t.add_row("Cleanup worktree on interrupt", "yes" if cleanup_on_exit else "no")
    t.add_row("Allow agent task pick", "yes" if allow_agent_pick else "no")
    t.add_row("Explicit task", task_arg if task_arg else f"(from {TASKS_DIR}/priorities.md)")
    t.add_row("Resuming prior cycle", "yes" if resuming else "no")
    if complete_worktree_mode:
        t.add_row("Orphan worktree recovery", "single cycle then exit")
    t.add_row("Generation", runner_id)
    if not session_deadline_epoch:
        t.add_row(
            "Max consecutive failures (no wall limit)",
            str(MAX_RESUME_ERRORS_UNLIMITED_SESSION),
        )
    console.print(Panel(t, border_style="cyan"))


def _cli_allows_prompts() -> bool:
    return sys.stdin.isatty()


def task_list_choice_paths(primary: Path, pending: list[Path]) -> list[str]:
    return [path.relative_to(primary).as_posix() for path in pending]


def _prompt_required(label: str, *, default: str | None = None) -> str:
    raw = Prompt.ask(label, default=default) if default is not None else Prompt.ask(label)
    value = raw.strip()
    if not value:
        console.print(f"[red]{label} is required.[/red]")
        raise typer.Exit(1)
    return value


def _backlog_task_paths(primary: Path) -> list[Path]:
    return sorted((primary / TASKS_DIR / "backlog").rglob("*.md"))


def _pick_existing_backlog_task(primary: Path) -> Path | None:
    pending = _backlog_task_paths(primary)
    if not pending:
        console.print("[yellow]No backlog tasks to refine yet; creating a new one.[/yellow]")
        return None
    choice_paths = task_list_choice_paths(primary, pending)
    table = Table(title="Backlog tasks")
    table.add_column("#")
    table.add_column("Task")
    for idx, rel_path in enumerate(choice_paths, 1):
        table.add_row(str(idx), rel_path)
    console.print(table)
    raw_idx = IntPrompt.ask("Choose task index", default=1)
    try:
        idx = resolve_choice_index(choice_count=len(choice_paths), raw_index=raw_idx)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    return pending[idx]


def _existing_task_defaults(task_path: Path) -> tuple[str, str, str]:
    text = task_path.read_text(encoding="utf-8", errors="replace")
    title_match = re.search(r"^task:\s*(.+)$", text, flags=re.MULTILINE)
    command_match = re.search(r"^test_command:\s*(.+)$", text, flags=re.MULTILINE)
    goal_match = re.search(r"(?ms)^# Goal\s+(.*?)(?:^## |\Z)", text)
    title = title_match.group(1).strip() if title_match else task_path.stem.replace("-", " ")
    goal = goal_match.group(1).strip() if goal_match else ""
    test_command = command_match.group(1).strip() if command_match else "uv run pytest -q"
    return title, goal, test_command


def _slugify_task_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "task"


def _next_task_path(primary: Path, title: str) -> Path:
    slug = _slugify_task_title(title)
    backlog = primary / TASKS_DIR / "backlog"
    candidate = backlog / f"{slug}.md"
    idx = 2
    while candidate.exists():
        candidate = backlog / f"{slug}-{idx}.md"
        idx += 1
    return candidate


def _task_markdown(*, title: str, goal: str, test_command: str) -> str:
    return (
        f"task: {title}\n"
        f"test_command: {test_command}\n\n"
        "# Goal\n\n"
        f"{goal}\n\n"
        "## Checklist\n\n"
        "- [ ] Write a concrete implementation plan\n"
        "- [ ] Implement the requested change\n"
        f"- [ ] Run `{test_command}`\n"
    )


def _plan_tasks_interactively(primary: Path) -> list[Path]:
    created: list[Path] = []
    backlog = primary / TASKS_DIR / "backlog"
    backlog.mkdir(parents=True, exist_ok=True)
    while True:
        existing_task: Path | None = None
        if _backlog_task_paths(primary) and Confirm.ask("Refine an existing backlog task?", default=False):
            existing_task = _pick_existing_backlog_task(primary)
        if existing_task is not None:
            title_default, goal_default, test_command_default = _existing_task_defaults(existing_task)
        else:
            title_default, goal_default, test_command_default = (None, None, "uv run pytest -q")
        title = _prompt_required("Task title", default=title_default)
        goal = _prompt_required("What do you want to achieve?", default=goal_default)
        test_command = _prompt_required("Verification command", default=test_command_default)
        task_path = existing_task or _next_task_path(primary, title)
        task_path.write_text(
            _task_markdown(title=title, goal=goal, test_command=test_command),
            encoding="utf-8",
        )
        created.append(task_path)
        verb = "Updated" if existing_task is not None else "Created"
        console.print(f"[green]{verb} task:[/green] {task_path.relative_to(primary)}")
        if not Confirm.ask("Add another task?", default=False):
            break
    refresh_priorities_from_backlog(primary)
    return created


@app.command("init")
def cmd_init() -> None:
    primary = resolve_git_repo_root(
        None,
        console=console,
        interactive=False,
    )
    if not _cli_allows_prompts():
        console.print("[red]`sponte init` requires an interactive terminal (stdin must be a TTY).[/red]")
        raise typer.Exit(1)
    if sponte_tasks_layout_valid(primary):
        console.print(f"[green]Workspace already initialized:[/green] {primary / '.sponte'}")
        raise typer.Exit(0)
    bootstrap_workspace_with_prompt(
        primary,
        console=console,
        interactive=True,
    )


@app.command("auto-focus")
def cmd_auto_focus(
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", "-w", help="Git checkout root (run from anywhere)"),
    ] = None,
    trunk_branch: Annotated[
        str | None,
        typer.Option("--trunk-branch", help="Override workspace trunk branch for worktrees/merges"),
    ] = None,
    task: Annotated[str | None, typer.Argument(help="Optional .sponte/tasks/… path")] = None,
    agent: Annotated[
        str,
        typer.Option("--agent", help="cursor | claude | codex | droid | oz | warp | amp"),
    ] = DEFAULT_AGENT,
    plan_model: Annotated[str, typer.Option("--plan-model", help="Model for plan phase")] = DEFAULT_PLAN_MODEL,
    execute_model: Annotated[str, typer.Option("--execute-model", help="Model for implement phases")] = DEFAULT_EXECUTE_MODEL,
    rotate_threshold_tokens: Annotated[
        int | None,
        typer.Option("--rotate-threshold-tokens", help="Rotate to fresh context at this token total (default: env/config)"),
    ] = None,
    warn_threshold_tokens: Annotated[
        int | None,
        typer.Option("--warn-threshold-tokens", help="Warn before rotation at this token total (default: env/config)"),
    ] = None,
    max_cycles: Annotated[int | None, typer.Option("--max-cycles", help="Stop after N successful cycles")] = None,
    once: Annotated[bool, typer.Option("--once", help="Exactly one full cycle")] = False,
    max_duration: Annotated[
        str | None,
        typer.Option("--max-duration", help="Wall limit e.g. 6h, 90m (default: no limit)"),
    ] = None,
    extend_duration: Annotated[
        str | None,
        typer.Option(
            "--extend-duration",
            help="Only with --resume: add wall time after max(now, stored deadline); ignored otherwise",
        ),
    ] = None,
    unlimited: Annotated[bool, typer.Option("--unlimited", help="No session wall-clock limit (default without --max-duration)")] = False,
    allow_agent_pick: Annotated[
        bool | None,
        typer.Option(
            "--allow-agent-pick/--no-allow-agent-pick",
            help="Let agent choose task; default yes if no task path, no if task given (not when resuming)",
        ),
    ] = None,
    cleanup_on_exit: Annotated[bool, typer.Option("--cleanup-on-exit")] = False,
    progress: Annotated[
        str | None,
        typer.Option("--progress", help="off | on | full (full = tee agent to terminal)"),
    ] = None,
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume",
            metavar="RUNNER_ID",
            help="Generation id to resume (same as session id / app-state ralph.lock runner_id)",
        ),
    ] = None,
    complete_worktree: Annotated[
        str | None,
        typer.Option(
            "--complete-worktree",
            metavar="PATH",
            help="Resume from saved state for this worktree path; run exactly one cycle and exit",
        ),
    ] = None,
    clear_resume_id: Annotated[
        str | None,
        typer.Option(
            "--clear-resume",
            metavar="RUNNER_ID",
            help="Clear saved state for this generation id only",
        ),
    ] = None,
    runner_id: Annotated[
        str | None,
        typer.Option(
            "--runner-id",
            help="Stable generation id for new sessions (default: random rap-… or RALPH_RUNNER_ID); not with --resume / --complete-worktree",
        ),
    ] = None,
    skip_preflight: Annotated[bool, typer.Option("--skip-preflight", hidden=True)] = False,
) -> None:
    primary = resolve_git_repo_root(
        workspace,
        console=console,
        interactive=_cli_allows_prompts(),
    )

    resume_runner = resume.strip() if resume else ""
    if resume is not None and not resume_runner:
        console.print("[red]--resume requires a non-empty generation id (e.g. --resume lane-a)[/red]")
        raise typer.Exit(1)
    resume_id: str | None = resume_runner if resume_runner else None

    cwt_arg = ""
    if complete_worktree is not None:
        cwt_arg = complete_worktree.strip()
        if not cwt_arg:
            console.print("[red]--complete-worktree requires a non-empty worktree path[/red]")
            raise typer.Exit(1)
        if resume_id is not None:
            console.print("[red]Do not combine --complete-worktree with --resume[/red]")
            raise typer.Exit(1)
        if task:
            console.print("[red]Do not pass a task path with --complete-worktree[/red]")
            raise typer.Exit(1)
        if runner_id is not None:
            console.print("[red]Do not combine --complete-worktree with --runner-id[/red]")
            raise typer.Exit(1)

    clear_runner = clear_resume_id.strip() if clear_resume_id else ""
    if clear_resume_id is not None and not clear_runner:
        console.print("[red]--clear-resume requires a non-empty generation id[/red]")
        raise typer.Exit(1)
    if clear_runner:
        if cwt_arg:
            console.print("[red]Do not combine --complete-worktree with --clear-resume[/red]")
            raise typer.Exit(1)
        if resume_id is not None:
            console.print("[red]Do not combine --resume with --clear-resume[/red]")
            raise typer.Exit(1)
        resume_clear_state(primary, runner_id=clear_runner)
        clear_ralph_lock_matching_runner(primary, clear_runner)
        console.print(f"Cleared {resume_path(primary, runner_id=clear_runner)}")
        raise typer.Exit(0)

    if resume_id is not None and runner_id is not None:
        console.print("[red]Do not combine --resume RUNNER_ID with --runner-id; the resume id is the generation[/red]")
        raise typer.Exit(1)

    if resume_id is None and not cwt_arg and not task:
        console.print(
            "[red]`sponte auto-focus` requires a task path, `--resume`, or `--complete-worktree`. "
            "Use `sponte plan` to create tasks first.[/red]"
        )
        raise typer.Exit(1)
    if resume_id is None and not cwt_arg:
        primary = resolve_primary_workspace(
            primary,
            console=console,
            interactive=False,
        )

    loaded_resume_state: ResumeState | None = None
    if cwt_arg:
        wt_resolved = Path(cwt_arg).expanduser().resolve()
        pair = resolve_runner_for_worktree(primary, wt_resolved)
        if pair is None:
            console.print(
                "[red]No unique saved resume state for that worktree under this workspace.[/red]"
            )
            raise typer.Exit(1)
        resume_session_id, _ = pair
        loaded_resume_state = load_resume(primary, runner_id=resume_session_id)
        if loaded_resume_state is None:
            console.print("[red]Could not load resume state for the resolved generation.[/red]")
            raise typer.Exit(1)
        resume_id = resume_session_id

    runner_id_effective = resume_id if resume_id is not None else _effective_runner_id(runner_id)

    if resume_id is not None and task:
        console.print("[red]Do not pass a task path when resuming (--resume / --complete-worktree)[/red]")
        raise typer.Exit(1)

    if resume_id is not None and not cwt_arg:
        loaded_resume_state = load_resume(
            primary,
            runner_id=runner_id_effective,
        )
        if loaded_resume_state is None:
            console.print("[red]Nothing to resume[/red]")
            raise typer.Exit(1)

    if allow_agent_pick is not None:
        allow_agent_pick_effective: bool = allow_agent_pick
    else:
        allow_agent_pick_effective = (resume_id is None) and (task is None)

    pm: ProgressMode
    if progress is None:
        pm = DEFAULT_PROGRESS  # type: ignore[assignment]
    elif progress in ("off", "on", "full"):
        pm = progress  # type: ignore[assignment]
    else:
        console.print("[red]--progress must be off, on, or full[/red]")
        raise typer.Exit(1)

    if loaded_resume_state is not None:
        effective_agent = loaded_resume_state.agent_kind or agent
        effective_plan_model = loaded_resume_state.plan_model or plan_model
        effective_execute_model = loaded_resume_state.agent_model or execute_model
        effective_allow_agent_pick = loaded_resume_state.allow_agent_pick.lower() == "true"
        effective_task_arg = loaded_resume_state.task_arg
    else:
        effective_agent = agent
        effective_plan_model = plan_model
        effective_execute_model = execute_model
        effective_allow_agent_pick = allow_agent_pick_effective
        effective_task_arg = task or ""

    if not skip_preflight:
        run_preflight(agent=effective_agent, console=console, verbose=pm != "off")

    harness = get_harness(effective_agent)

    complete_worktree_mode = bool(cwt_arg)

    mc = max_cycles
    if once or complete_worktree_mode:
        mc = 1

    duration_sec: int | None
    if unlimited or once or complete_worktree_mode:
        duration_sec = None
    elif max_duration:
        duration_sec = parse_duration_to_seconds(max_duration)
    else:
        duration_sec = None

    deadline_epoch: str = ""
    if duration_sec is not None:
        deadline_epoch = str(time.time() + duration_sec)

    cfg = AutoFocusConfig(
        primary=primary,
        harness=harness,
        plan_model=effective_plan_model,
        execute_model=effective_execute_model,
        progress=pm,
        allow_agent_pick=effective_allow_agent_pick,
        cleanup_on_exit=cleanup_on_exit,
        task_arg=effective_task_arg,
        runner_id=runner_id_effective,
        trunk_branch_override=trunk_branch,
        rotate_policy=rotation_policy_from_overrides(
            rotate_threshold=rotate_threshold_tokens,
            warn_threshold=warn_threshold_tokens,
            default_rotate_threshold=ROTATE_THRESHOLD_TOKENS,
            default_warn_threshold=ROTATE_WARN_THRESHOLD_TOKENS,
        ),
    )
    max_cycles_str = str(mc) if mc is not None else ""

    cycles_done = 0
    invocation_cycles_done = 0
    use_resume_flag = resume_id is not None
    resume_state_for_cycle = loaded_resume_state
    if resume_id is not None:
        st = loaded_resume_state
        assert st is not None
        cycles_done = st.cycles_done
        if complete_worktree_mode:
            cfg.session_deadline_epoch = ""
        else:
            cfg.session_deadline_epoch = compute_resumed_deadline(
                stored_deadline_epoch=st.session_deadline_epoch,
                default_deadline_epoch=deadline_epoch,
                extend_duration=extend_duration or "",
                now_epoch=time.time(),
            )
        use_resume_flag = True
    else:
        cfg.session_deadline_epoch = deadline_epoch

    cfg.max_cycles_str = max_cycles_str
    stats = cfg.stats

    def on_signal(_sig: int, _frame: object | None) -> None:
        if cleanup_on_exit and cfg.current_wt_path and cfg.current_wt_path.is_dir():
            from ralph_focus.git_ops import git

            git(primary, "worktree", "remove", "-f", str(cfg.current_wt_path))
            resume_clear_state(
                primary,
                runner_id=runner_id_effective,
            )
        console.print("[yellow]Interrupted[/yellow]")
        sys.exit(130)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    consecutive_cycle_errors = 0
    _print_auto_focus_settings(
        primary=primary,
        agent=effective_agent,
        plan_model=effective_plan_model,
        execute_model=effective_execute_model,
        rotate_threshold_tokens=cfg.rotate_policy.rotate_threshold,
        warn_threshold_tokens=cfg.rotate_policy.warn_threshold,
        max_cycles=mc,
        once=once,
        duration_sec=duration_sec,
        session_deadline_epoch=cfg.session_deadline_epoch,
        progress=pm,
        cleanup_on_exit=cleanup_on_exit,
        allow_agent_pick=effective_allow_agent_pick,
        task_arg=effective_task_arg,
        resuming=use_resume_flag,
        runner_id=runner_id_effective,
        complete_worktree_mode=complete_worktree_mode,
    )

    try:
        while True:
            cycles_done_for_limit = invocation_cycles_done if complete_worktree_mode else cycles_done
            if mc is not None and cycles_done_for_limit >= mc:
                stats.exit_reason = "max_cycles"
                break
            if cfg.session_deadline_epoch:
                try:
                    if time.time() > float(cfg.session_deadline_epoch):
                        stats.exit_reason = "session_deadline"
                        break
                except ValueError:
                    pass

            cfg.cycles_done_entry = cycles_done
            cfg.max_cycles_str = max_cycles_str
            remaining: float | None = None
            if cfg.session_deadline_epoch:
                try:
                    remaining = float(cfg.session_deadline_epoch) - time.time()
                except ValueError:
                    remaining = None
            write_ralph_lock(
                primary,
                runner_id=runner_id_effective,
                session_cycle=cycles_done + 1,
                resuming_this_cycle=use_resume_flag,
            )
            if pm != "off":
                cycle_line(
                    cycles_done + 1,
                    mc,
                    remaining,
                    generation_id=runner_id_effective,
                )

            rc = run_one_cycle(
                cfg,
                use_resume=use_resume_flag,
                resume_state=resume_state_for_cycle,
                stop_after_plan=False,
            )
            use_resume_flag = False
            resume_state_for_cycle = None
            if rc == 2:
                stats.exit_reason = "no_actionable_task"
                break
            if rc == 3:
                stats.exit_reason = "token_rotation"
                handoff_path = _write_rotation_handoff(
                    primary=primary,
                    runner_id=runner_id_effective,
                    stats=stats,
                    rotate_threshold_tokens=cfg.rotate_policy.rotate_threshold,
                )
                if handoff_path is not None:
                    _print_rotation_handoff_inline(
                        path=handoff_path,
                        content=handoff_path.read_text(encoding="utf-8", errors="replace"),
                    )
                console.print(f"[yellow]{_token_rotation_notice(rotate_threshold_tokens=cfg.rotate_policy.rotate_threshold)}[/yellow]")
                break
            if rc != 0:
                resume_st = load_resume(
                    primary,
                    runner_id=runner_id_effective,
                )
                failure_kind = cfg.last_failure_kind
                failure_detail = cfg.last_failure_detail.strip()
                if failure_kind in (FailureKind.GUTTER, FailureKind.FATAL):
                    stats.exit_reason = failure_kind.value
                    if failure_detail:
                        console.print(f"[red]{failure_detail}[/red]")
                        _print_disk_full_resume_hint(
                            failure_detail,
                            runner_id=runner_id_effective,
                        )
                    raise typer.Exit(1)
                has_deadline = bool(cfg.session_deadline_epoch)
                if rc == 1 and resume_st is not None:
                    if has_deadline:
                        try:
                            end = float(cfg.session_deadline_epoch)
                            if time.time() >= end:
                                stats.exit_reason = "session_deadline"
                                break
                        except ValueError:
                            has_deadline = False

                    consecutive_cycle_errors += 1
                    stats.resume_retries += 1
                    if not has_deadline and consecutive_cycle_errors >= MAX_RESUME_ERRORS_UNLIMITED_SESSION:
                        stats.exit_reason = "max_resume_errors"
                        console.print(
                            "[red]Too many consecutive cycle errors while session has no wall-clock limit; "
                            "use --max-duration, fix the agent, or clear resume.[/red]"
                        )
                        raise typer.Exit(1)

                    delay = min(60.0, 2.0 ** min(consecutive_cycle_errors, 6))
                    if has_deadline:
                        try:
                            end = float(cfg.session_deadline_epoch)
                            delay = min(delay, max(0.5, end - time.time()))
                        except ValueError:
                            pass

                    log_hint = resume_st.logf
                    console.print(
                        f"[yellow]Cycle step failed ({consecutive_cycle_errors}); "
                        f"retrying from resume in {delay:.1f}s — log: {log_hint}[/yellow]"
                    )
                    _print_disk_full_resume_hint(
                        failure_detail,
                        runner_id=runner_id_effective,
                    )
                    time.sleep(delay)
                    use_resume_flag = True
                    resume_state_for_cycle = None
                    continue

                raise typer.Exit(rc)
            consecutive_cycle_errors = 0
            cycles_done += 1
            invocation_cycles_done += 1
            cfg.task_arg = ""
    except typer.Exit:
        raise
    except Exception as exc:
        detail = _format_exception_detail(exc)
        _print_disk_full_resume_hint(detail, runner_id=runner_id_effective)
        raise
    finally:
        finalize_ralph_lock_if_session_idle(primary, runner_id_effective)
        if cfg.current_wt_path and cfg.current_wt_path.is_dir() and not cleanup_on_exit:
            console.print(
                f"[yellow]Worktree left for inspection:[/yellow] {cfg.current_wt_path}\n"
                f"Resume with: sponte auto-focus --resume "
                f"{shlex.quote(runner_id_effective)} --plan-model auto --execute-model auto"
            )

    _print_session_summary(
        stats,
        deadline_hit=stats.exit_reason == "session_deadline",
        runner_id=runner_id_effective,
    )


def _print_session_summary(stats: SessionStats, *, deadline_hit: bool, runner_id: str) -> None:
    wall = time.time() - stats.started_wall
    t = Table(title="Sponte session summary")
    t.add_column("Metric")
    t.add_column("Value")
    t.add_row("Generation (resume id)", runner_id)
    t.add_row("Wall time (s)", f"{wall:.1f}")
    t.add_row("Cycles completed", str(stats.cycles_completed))
    t.add_row("Resume retries", str(stats.resume_retries))
    t.add_row("Agent steps", str(stats.agent_steps))
    t.add_row("Merge conflict rounds", str(stats.merge_conflict_rounds))
    t.add_row("Exit reason", stats.exit_reason or "normal")
    if stats.rotation_tokens() > 0:
        t.add_row("Rotation tokens", str(stats.rotation_tokens()))
    if stats.token_totals:
        t.add_row("Token totals", ", ".join(f"{k}={v}" for k, v in sorted(stats.token_totals.items())))
    console.print(Panel(t, border_style="green"))
    if deadline_hit:
        console.print("[dim]Session wall-clock limit reached.[/dim]")


@app.command("worktree-prune-clean")
def cmd_prune(
    force: Annotated[bool, typer.Option("--force")] = False,
    workspace_opt: Annotated[
        Path | None,
        typer.Option("--workspace", "-w", help="Git checkout root"),
    ] = None,
    path: Annotated[Path | None, typer.Argument()] = None,
) -> None:
    pick = workspace_opt or path
    ws = resolve_git_repo_root(
        pick,
        console=console,
        interactive=_cli_allows_prompts(),
    )
    raise typer.Exit(worktree_prune_clean(ws, force=force, console=console))


@app.command("worktree-remove")
def cmd_remove(
    workspace_opt: Annotated[
        Path | None,
        typer.Option("--workspace", "-w", help="Git checkout root"),
    ] = None,
    path: Annotated[Path | None, typer.Argument()] = None,
) -> None:
    pick = workspace_opt or path
    ws = resolve_git_repo_root(
        pick,
        console=console,
        interactive=_cli_allows_prompts(),
    )
    raise typer.Exit(worktree_remove_interactive(ws, console=console))


@app.command("plan")
def cmd_plan(
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", "-w", help="Git checkout root (run from anywhere)"),
    ] = None,
) -> None:
    primary = resolve_git_repo_root(
        workspace,
        console=console,
        interactive=True,
    )
    primary = resolve_primary_workspace(
        primary,
        console=console,
        interactive=False,
    )
    if not _cli_allows_prompts():
        console.print("[red]`sponte plan` requires an interactive terminal (stdin must be a TTY).[/red]")
        raise typer.Exit(1)
    created = _plan_tasks_interactively(primary)
    console.print(f"[green]Planned {len(created)} task(s) in[/green] {primary / TASKS_DIR}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
