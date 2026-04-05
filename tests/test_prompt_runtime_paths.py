from pathlib import Path

from config.defaults import LEGACY_TASKS_DIR, SPONTE_GUARDRAILS_PATH, TASKS_DIR
from ralph_focus.paths import next_task_file


def test_render_prompt_uses_sponte_guardrails_path(tmp_path: Path) -> None:
    from ralph_focus.prompts import render_prompt

    rendered = render_prompt(
        "plan",
        primary=tmp_path,
        task_rel=f"{TASKS_DIR}/backlog/example.md",
        plan_rel="/tmp/plan.md",
    )

    assert SPONTE_GUARDRAILS_PATH in rendered
    assert ".agents/" not in rendered


def test_render_prompt_injects_next_task_file_for_agent_pick(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "state"))

    from ralph_focus.prompts import render_prompt

    rendered = render_prompt("agent_pick_task", primary=tmp_path, task_rel="", plan_rel="")

    assert f"{TASKS_DIR}/backlog/*.md" in rendered
    assert str(next_task_file(tmp_path)) in rendered
    assert ".agents/" not in rendered


def test_render_prompt_uses_legacy_task_root_when_repo_still_uses_legacy_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "state"))
    legacy_priorities = tmp_path / LEGACY_TASKS_DIR / "priorities.md"
    legacy_priorities.parent.mkdir(parents=True, exist_ok=True)
    legacy_priorities.write_text("- [Demo](./backlog/demo.md)\n", encoding="utf-8")

    from ralph_focus.prompts import render_prompt

    rendered = render_prompt("agent_pick_task", primary=tmp_path, task_rel="", plan_rel="")

    assert f"{LEGACY_TASKS_DIR}/backlog/*.md" in rendered


def test_rendered_active_prompts_mention_workspace_instruction_files(tmp_path: Path) -> None:
    from ralph_focus.prompts import render_prompt

    for name in ("plan", "implement", "improve", "verify"):
        rendered = render_prompt(
            name,
            primary=tmp_path,
            task_rel=f"{TASKS_DIR}/backlog/example.md",
            plan_rel="/tmp/plan.md",
        )
        assert "AGENTS.md" in rendered
        assert "CLAUDE.md" in rendered
