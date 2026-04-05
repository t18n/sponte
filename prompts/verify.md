# Verify before merge

Read `__TASK_FILE__`, `__PLAN_FILE__`, `__GUARDRAILS_FILE__`, and `__PROGRESS_FILE__`.
Also read workspace instruction files such as `AGENTS.md` and `CLAUDE.md` if they exist.

Run the configured verification commands:
__VERIFY_COMMANDS__

Review the current task outcome with planner/reviewer judgment:
- confirm the task scope appears complete
- confirm each acceptance criterion has evidence
- confirm the verification results are reflected in `__PROGRESS_FILE__`
- note any remaining risks or follow-ups

If you learn a durable lesson that should guide future runs, update `__GUARDRAILS_FILE__` briefly.

This is a verification/review phase. Prefer recording findings over broad new implementation churn.
