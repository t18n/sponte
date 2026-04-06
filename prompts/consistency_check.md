# Consistency check (plan only)

Read `__TASK_FILE__`, the current plan at `__PLAN_FILE__`, and `__PROGRESS_FILE__` if present.
Also read workspace instruction files such as `AGENTS.md` and `CLAUDE.md` if they exist.

Compare the **implementation in this branch** to the **rest of the repository**: architecture, naming, error handling, tests, security boundaries, and how the change fits existing patterns.

**Do not implement code in this phase.** Propose concrete adjustments only.

Append a short **"## Consistency check"** section to `__PROGRESS_FILE__` with:

- what aligns well with the codebase
- concrete mismatches, risks, or missing coverage
- the most important fixes for the next implement pass (ordered)

If the implementation is already consistent with the broader repo, state that explicitly and avoid unnecessary churn.
