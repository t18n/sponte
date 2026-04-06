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

    assert TASKS_DIR in rendered
    assert str(next_task_file(tmp_path)) in rendered
    assert ".agents/" not in rendered
    assert "__BACKLOG_CANDIDATES__" not in rendered
    assert "__CLAIMED_TASKS__" not in rendered


def test_render_prompt_uses_legacy_task_root_when_repo_still_uses_legacy_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "state"))
    legacy_priorities = tmp_path / LEGACY_TASKS_DIR / "priorities.md"
    legacy_priorities.parent.mkdir(parents=True, exist_ok=True)
    legacy_priorities.write_text("- [Demo](./backlog/demo.md)\n", encoding="utf-8")

    from ralph_focus.prompts import render_prompt

    rendered = render_prompt("agent_pick_task", primary=tmp_path, task_rel="", plan_rel="")

    assert LEGACY_TASKS_DIR in rendered


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


def test_render_prompt_resolves_workspace_prompt_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPONTE_STATE_DIR", str(tmp_path / "state"))
    from ralph_focus.prompts import render_prompt, resolve_prompt_template_path
    from ralph_focus.workspace_settings import WorkspaceSettings, save_workspace_settings

    (tmp_path / ".sponte").mkdir(parents=True)
    custom = tmp_path / ".sponte" / "prompts" / "pick.md"
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_text("# Workspace override\nPick to __NEXT_TASK_FILE__\n", encoding="utf-8")
    save_workspace_settings(
        tmp_path,
        WorkspaceSettings(prompts={"agent_pick_task": ".sponte/prompts/pick.md"}),
    )

    assert resolve_prompt_template_path("agent_pick_task", tmp_path) == custom
    rendered = render_prompt("agent_pick_task", primary=tmp_path, task_rel="", plan_rel="")
    assert "Workspace override" in rendered
