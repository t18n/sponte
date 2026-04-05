# Plan phase (write only the plan file)

Read `__TASK_FILE__`, `__GUARDRAILS_FILE__` if present, and `__PROGRESS_FILE__` if present.
Also read workspace instruction files such as `AGENTS.md` and `CLAUDE.md` if they exist.

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
