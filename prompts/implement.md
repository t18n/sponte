# Implement phase

Read `__TASK_FILE__`, `__PLAN_FILE__`, `__GUARDRAILS_FILE__`, and `__PROGRESS_FILE__`.
Also read workspace instruction files such as `AGENTS.md` and `CLAUDE.md` if they exist.

Use `__TASK_STATUS_FILE__` as the completion marker for this task:
- when the task scope is complete, set `"completed": true`
- if more work is still needed, leave `"completed": false`
- keep other fields intact unless you are intentionally updating them

This is an executor/remediation phase:
- follow the planner-authored plan
- if `__PROGRESS_FILE__` contains planner review feedback, address the highest-priority remediation items first
- keep changes tightly scoped to satisfying the task and planner feedback

Run the task `test_command` from frontmatter when reasonable and fix failures.

Update `__PROGRESS_FILE__` with what you did.

If you learn a durable lesson that should guide future runs, update `__GUARDRAILS_FILE__` briefly.
