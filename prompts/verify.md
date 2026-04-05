# Verify before merge

Read `__TASK_FILE__`, `__PLAN_FILE__`, `.agents/ralph/guardrails.md`, and `.agents/ralph/progress.md`.

Run the configured verification commands:
__VERIFY_COMMANDS__

Review the current task outcome with planner/reviewer judgment:
- confirm the task scope appears complete
- confirm each acceptance criterion has evidence
- confirm the verification results are reflected in `.agents/ralph/progress.md`
- note any remaining risks or follow-ups

If you learn a durable lesson that should guide future runs, update `.agents/ralph/guardrails.md` briefly.

This is a verification/review phase. Prefer recording findings over broad new implementation churn.
