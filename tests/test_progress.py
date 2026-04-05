from ralph_focus.progress import format_phase_bar_line, format_step_done_line, max_agent_steps


def test_phase_bar_line_includes_model_and_tokens() -> None:
    line = format_phase_bar_line(2, 10, "IMPLEMENT_2", model="gpt-5", token_total=12_345)
    assert "IMPLEMENT_2" in line
    assert "model=gpt-5" in line
    assert "tokens=12,345" in line


def test_step_done_line_includes_model_and_tokens() -> None:
    line = format_step_done_line("VERIFY", "wall_s=1.2", model="planner", token_total=80_000)
    assert "VERIFY" in line
    assert "model=planner" in line
    assert "tokens=80,000" in line


def test_max_agent_steps_includes_verify_phase() -> None:
    assert max_agent_steps(implement_max=15, improve_implement_max=5, conflict_max=5) == 43
