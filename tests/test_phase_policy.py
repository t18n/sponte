from ralph_focus.phase_policy import phase_model_for, phase_uses_agent


def test_planner_owns_plan_improve_and_verify() -> None:
    for phase in ("PLAN", "IMPROVE", "IMPROVE_REVIEW", "CONSISTENCY_REVIEW", "VERIFY"):
        assert phase_model_for(phase, plan_model="planner", execute_model="executor") == "planner"


def test_executor_owns_implementation_and_remediation_phases() -> None:
    for phase in (
        "IMPLEMENT",
        "IMPROVE_EXECUTE",
        "CONSISTENCY_EXECUTE",
        "WRAP",
        "MERGE_CONFLICT",
        "PRIMARY_PREMERGE",
    ):
        assert phase_model_for(phase, plan_model="planner", execute_model="executor") == "executor"


def test_merge_is_not_agent_driven() -> None:
    assert phase_uses_agent("MERGE") is False
    assert phase_uses_agent("MERGE_CONFLICT") is True
