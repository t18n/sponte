# Implement phase

Read `__TASK_FILE__`, `__PLAN_FILE__`, `.agents/ralph/guardrails.md`, `.agents/ralph/progress.md`.

Implement until **every** checklist item in `__TASK_FILE__` is `[x]` (no remaining `[ ]`).

This is an executor/remediation phase:
- follow the planner-authored plan
- if `.agents/ralph/progress.md` contains planner review feedback, address the highest-priority remediation items first
- keep changes tightly scoped to satisfying the task and planner feedback

Run the task `test_command` from frontmatter when reasonable and fix failures.

Update `.agents/ralph/progress.md` with what you did.

If you learn a durable lesson that should guide future runs, update `.agents/ralph/guardrails.md` briefly.

Do not edit `__TASK_FILE__` checkboxes until work is done; then mark all criteria complete.
