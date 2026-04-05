"""Resume file layout: ``agent/`` writes with legacy ``auto-focus/`` read fallback."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from config.defaults import RESUME_SCHEMA_VERSION
from ralph_focus.paths import resume_file, resume_file_legacy
from ralph_focus.resume import ResumeState, clear_resume, load_resume, write_resume


def test_load_resume_reads_legacy_when_agent_missing(tmp_path: Path) -> None:
    rid = "lane-a"
    st = ResumeState(
        schema_version=RESUME_SCHEMA_VERSION,
        primary=str(tmp_path.resolve()),
        phase="WRAP",
        logf="/l.log",
        wt_path="/w",
        rel_task=".sponte/tasks/in-progress/t.md",
        resume_runner_id=rid,
    )
    write_resume(tmp_path, st, runner_id=rid)
    agent = resume_file(tmp_path, runner_id=rid)
    legacy = resume_file_legacy(tmp_path, runner_id=rid)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(agent.read_bytes())
    agent.unlink()

    loaded = load_resume(tmp_path, runner_id=rid)
    assert loaded is not None
    assert loaded.phase == "WRAP"

    write_resume(tmp_path, replace(st, phase="PLAN"), runner_id=rid)
    loaded2 = load_resume(tmp_path, runner_id=rid)
    assert loaded2 is not None
    assert loaded2.phase == "PLAN"


def test_clear_resume_removes_both_locations(tmp_path: Path) -> None:
    rid = "r1"
    st = ResumeState(
        schema_version=RESUME_SCHEMA_VERSION,
        primary=str(tmp_path.resolve()),
        phase="PLAN",
        logf="/l.log",
        wt_path="/w",
        rel_task=".sponte/tasks/in-progress/t.md",
    )
    write_resume(tmp_path, st, runner_id=rid)
    agent = resume_file(tmp_path, runner_id=rid)
    legacy = resume_file_legacy(tmp_path, runner_id=rid)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(agent.read_bytes())

    clear_resume(tmp_path, runner_id=rid)
    assert not agent.is_file()
    assert not legacy.is_file()
