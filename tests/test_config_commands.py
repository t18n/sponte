import importlib

import config.commands as commands


def test_default_verify_commands_use_sponte(monkeypatch) -> None:
    monkeypatch.delenv("RALPH_VERIFY_COMMANDS", raising=False)

    reloaded = importlib.reload(commands)

    assert reloaded.VERIFY_COMMANDS == ("python -m ralph_focus.smoke_tests",)
