# Implement phase

Read `__TASK_FILE__`, `__PLAN_FILE__`, `__GUARDRAILS_FILE__`, and `__PROGRESS_FILE__`.
Also read workspace instruction files such as `AGENTS.md` and `CLAUDE.md` if they exist.

Implement until **every** checklist item in `__TASK_FILE__` is `[x]` (no remaining `[ ]`).

This is an executor/remediation phase:
- follow the planner-authored plan
- if `__PROGRESS_FILE__` contains planner review feedback, address the highest-priority remediation items first
- keep changes tightly scoped to satisfying the task and planner feedback

Run the task `test_command` from frontmatter when reasonable and fix failures.

Update `__PROGRESS_FILE__` with what you did.

If you learn a durable lesson that should guide future runs, update `__GUARDRAILS_FILE__` briefly.

Do not edit `__TASK_FILE__` checkboxes until work is done; then mark all criteria complete.
