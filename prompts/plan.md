# Plan phase (write only the plan file)

Read `__TASK_FILE__`, `.agents/ralph/guardrails.md` if present, and `.agents/ralph/progress.md` if present.

Overwrite `__PLAN_FILE__` with a concise markdown plan containing:
- goal
- files likely to change
- ordered implementation steps
- explicit acceptance criteria / done checks
- test command from task frontmatter
- verification notes, including these commands when relevant:
__VERIFY_COMMANDS__

Rules: modify only `__PLAN_FILE__`. Do not implement code in this phase.

Reply with one line confirming the plan path when done.
