import pytest
from typer.testing import CliRunner

from ralph_focus.interactive_setup import resolve_choice_index


def test_invalid_choice_index_is_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_choice_index(choice_count=3, raw_index=0)
    with pytest.raises(ValueError):
        resolve_choice_index(choice_count=3, raw_index=4)


def test_help_hides_removed_commands() -> None:
    from ralph_focus import cli

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    output = result.stdout.lower()
    assert "init" in output
    assert "plan" in output
    assert "auto-focus" in output
    assert "interactive" not in output
    assert "smoke" not in output
