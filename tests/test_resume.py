from pathlib import Path

import pytest

from config.defaults import TASKS_DIR
from ralph_focus.paths import plan_file_for_task, resume_file
from ralph_focus.resume import ResumeState, load_resume, write_resume


def test_resume_round_trips_token_and_progress_counters(tmp_path: Path) -> None:
    state = ResumeState(
        primary=str(tmp_path.resolve()),
        logf=str(tmp_path / "run.log"),
        wt_path=str(tmp_path / "wt"),
        rel_task=f"{TASKS_DIR}/in-progress/example.md",
        total_tokens=1234,
        no_progress_loops=2,
        token_warning_emitted="true",
    )

    write_resume(tmp_path, state, runner_id="lane-a")
    loaded = load_resume(tmp_path, runner_id="lane-a")

    assert loaded is not None
    assert loaded.resume_runner_id == "lane-a"
    assert loaded.total_tokens == 1234


def test_resume_runner_id_persists_when_set(tmp_path: Path) -> None:
    state = ResumeState(
        primary=str(tmp_path.resolve()),
        logf=str(tmp_path / "run.log"),
        wt_path=str(tmp_path / "wt"),
        rel_task=f"{TASKS_DIR}/in-progress/example.md",
        resume_runner_id="rap-deadbeef",
    )
    write_resume(tmp_path, state, runner_id="rap-deadbeef")
    loaded = load_resume(tmp_path, runner_id="rap-deadbeef")
    assert loaded is not None
    assert loaded.resume_runner_id == "rap-deadbeef"


def test_load_resume_returns_none_for_invalid_numeric_field(tmp_path: Path) -> None:
    resume_path = resume_file(tmp_path, runner_id="lane-a")
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_text(
        "\n".join(
            [
                "# ralph resume (generated; do not hand-edit)",
                f"export R_RESUME_SCHEMA_VERSION='2'",
                f"export R_RESUME_PRIMARY='{tmp_path.resolve()}'",
                f"export R_RESUME_PHASE='PLAN'",
                f"export R_RESUME_LOGF='{tmp_path / 'run.log'}'",
                f"export R_RESUME_WT_PATH='{tmp_path / 'wt'}'",
                f"export R_RESUME_REL_TASK='{TASKS_DIR}/in-progress/example.md'",
                "export R_RESUME_TOTAL_TOKENS='not-a-number'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert load_resume(tmp_path, runner_id="lane-a") is None


def test_load_resume_returns_none_for_invalid_schema_field(tmp_path: Path) -> None:
    resume_path = resume_file(tmp_path, runner_id="lane-a")
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_text(
        "\n".join(
            [
                "# ralph resume (generated; do not hand-edit)",
                "export R_RESUME_SCHEMA_VERSION='bogus'",
                f"export R_RESUME_PRIMARY='{tmp_path.resolve()}'",
                f"export R_RESUME_LOGF='{tmp_path / 'run.log'}'",
                f"export R_RESUME_WT_PATH='{tmp_path / 'wt'}'",
                f"export R_RESUME_REL_TASK='{TASKS_DIR}/in-progress/example.md'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert load_resume(tmp_path, runner_id="lane-a") is None


def test_load_resume_migrates_legacy_task_and_plan_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "st"))
    resume_path = resume_file(tmp_path, runner_id="lane-a")
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    expected_plan = plan_file_for_task(tmp_path, "example")
    resume_path.write_text(
        "\n".join(
            [
                "# ralph resume (generated; do not hand-edit)",
                "export R_RESUME_SCHEMA_VERSION='2'",
                f"export R_RESUME_PRIMARY='{tmp_path.resolve()}'",
                "export R_RESUME_PHASE='PLAN'",
                f"export R_RESUME_LOGF='{tmp_path / 'run.log'}'",
                f"export R_RESUME_WT_PATH='{tmp_path / 'wt'}'",
                "export R_RESUME_REL_TASK='.agents/tasks/in-progress/example.md'",
                "export R_RESUME_PLAN_REL='.agents/ralph/data/plans/example.md'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_resume(tmp_path, runner_id="lane-a")

    assert loaded is not None
    assert loaded.rel_task == f"{TASKS_DIR}/in-progress/example.md"
    assert loaded.plan_rel == expected_plan.resolve().as_posix()
