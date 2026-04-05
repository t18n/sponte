import importlib
from pathlib import Path

import pytest


def test_default_verify_commands_use_sponte(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RALPH_VERIFY_COMMANDS", raising=False)

    import config.commands as commands

    reloaded = importlib.reload(commands)

    assert reloaded.VERIFY_COMMANDS == ("python -m ralph_focus.smoke_tests",)


def test_resolved_verify_prefers_workspace_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RALPH_VERIFY_COMMANDS", "echo global")
    import config.commands as commands_mod

    reloaded = importlib.reload(commands_mod)

    from ralph_focus.workspace_settings import (
        WorkspaceCommandSettings,
        WorkspaceSettings,
        save_workspace_settings,
    )

    root = tmp_path / "repo"
    root.mkdir()
    save_workspace_settings(
        root,
        WorkspaceSettings(
            commands=WorkspaceCommandSettings(verify=("pnpm run check", "pnpm run test")),
        ),
    )

    assert reloaded.resolved_verify_commands(root) == ("pnpm run check", "pnpm run test")
    assert reloaded.resolved_verify_commands(None) == ("echo global",)


def test_verify_commands_markdown_uses_workspace_verify(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RALPH_VERIFY_COMMANDS", raising=False)

    import config.commands as commands_mod

    reloaded = importlib.reload(commands_mod)

    from ralph_focus.workspace_settings import (
        WorkspaceCommandSettings,
        WorkspaceSettings,
        save_workspace_settings,
    )

    root = tmp_path / "repo"
    root.mkdir()
    save_workspace_settings(
        root,
        WorkspaceSettings(commands=WorkspaceCommandSettings(verify=("step-one", "step-two"))),
    )

    md = reloaded.verify_commands_markdown(root)
    assert "- `step-one`" in md
    assert "- `step-two`" in md
