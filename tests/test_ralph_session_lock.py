from pathlib import Path

from ralph_focus.ralph_session_lock import write_ralph_lock


def test_write_ralph_lock_uses_sponte_resume_hint(tmp_path: Path) -> None:
    write_ralph_lock(
        tmp_path,
        runner_id="rap-test1234",
        session_cycle=1,
        resuming_this_cycle=False,
    )

    rendered = (tmp_path / ".agents" / "ralph" / "ralph.lock").read_text(encoding="utf-8")

    assert "sponte auto-focus --resume rap-test1234" in rendered
