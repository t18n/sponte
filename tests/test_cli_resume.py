from io import StringIO

from rich.console import Console

from ralph_focus.cli import (
    _disk_full_resume_hint,
    _format_exception_detail,
    _print_rotation_handoff_inline,
    _token_rotation_notice,
    _rotation_handoff_markdown,
    compute_resumed_deadline,
)
from ralph_focus.resume import ResumeState
from ralph_focus.session_stats import SessionStats


def test_compute_resumed_deadline_extends_existing_deadline() -> None:
    result = compute_resumed_deadline(
        stored_deadline_epoch="150",
        default_deadline_epoch="",
        extend_duration="10",
        now_epoch=100.0,
    )

    assert result == "160.0"


def test_compute_resumed_deadline_creates_deadline_when_missing() -> None:
    result = compute_resumed_deadline(
        stored_deadline_epoch="",
        default_deadline_epoch="",
        extend_duration="10",
        now_epoch=100.0,
    )

    assert result == "110.0"


def test_disk_full_resume_hint_includes_resume_command() -> None:
    result = _disk_full_resume_hint(
        "OSError: [Errno 28] No space left on device",
        runner_id="rap-test1234",
    )

    assert result is not None
    assert "disk appears full" in result
    assert "sponte auto-focus --resume rap-test1234" in result


def test_disk_full_resume_hint_returns_none_for_other_failures() -> None:
    result = _disk_full_resume_hint(
        "HTTP 429 rate limit exceeded",
        runner_id="rap-test1234",
    )

    assert result is None


def test_format_exception_detail_includes_exception_type() -> None:
    result = _format_exception_detail(OSError(28, "No space left on device"))

    assert result == "OSError: [Errno 28] No space left on device"


def test_rotation_handoff_markdown_includes_resume_context() -> None:
    stats = SessionStats(cycles_completed=1, agent_steps=4)
    stats.rotation_token_count = 79_500
    state = ResumeState(
        primary="/repo",
        phase="IMPLEMENT",
        logf="/home/u/.local/state/sponte/workspaces/abc/runners/rap-test1234/auto-focus/logs/run.log",
        wt_path="/repo/.sponte/worktrees/task-1234",
        rel_task=".sponte/tasks/in-progress/example.md",
        plan_rel="/home/u/.local/state/sponte/workspaces/abc/plans/example.md",
    )

    result = _rotation_handoff_markdown(
        runner_id="rap-test1234",
        resume_state=state,
        stats=stats,
        rotate_threshold_tokens=80_000,
        task_title="Example task",
        pending_count=2,
        done_count=5,
    )

    assert "Rotation handoff" in result
    assert "`IMPLEMENT`" in result
    assert "`Example task`" in result
    assert "post-step trigger, not a hard cap" in result
    assert "`80,000`" in result
    assert "`79,500`" in result
    assert "sponte auto-focus --resume rap-test1234" in result


def test_print_rotation_handoff_inline_renders_content(monkeypatch) -> None:
    from ralph_focus import cli

    out = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=out, force_terminal=False, color_system=None))

    _print_rotation_handoff_inline(
        path="/home/u/.local/state/sponte/workspaces/abc/runners/rap-test1234/auto-focus/rotation-handoff.md",
        content="# Rotation handoff\n\n- Current phase: `IMPLEMENT`\n",
    )

    rendered = out.getvalue()
    assert "Rotation handoff written" in rendered
    assert "rap-test1234" in rendered
    assert "auto-focus" in rendered
    assert "Current phase" in rendered
    assert "IMPLEMENT" in rendered


def test_token_rotation_notice_clarifies_post_step_trigger() -> None:
    result = _token_rotation_notice(rotate_threshold_tokens=80_000)

    assert "after the completed step" in result
    assert "80,000" in result
    assert "hard cap" not in result
