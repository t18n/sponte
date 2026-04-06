# Pick the next backlog task (plan phase)

You are choosing **one** task for this Sponte session. Use the **plan model** reasoning: read the repository (code, structure, recent changes if helpful), the task store, and what is already in flight.

## Inputs (do not ignore)

**Claimed / in-flight tasks** (other sessions may be working these — prefer work that is **least overlapping** with these paths and goals):

__CLAIMED_TASKS__

**Pending backlog candidates** (each path must still exist under `__TASKS_ROOT__/backlog/` and have open checklist items):

__BACKLOG_CANDIDATES__

Optional context files (if present): `__GUARDRAILS_FILE__`, `AGENTS.md`, `CLAUDE.md`, `__PROGRESS_FILE__`.

## Selection goals (in order)

1. **Conflict avoidance:** Prefer a task whose files/areas are **least related** to the claimed tasks above (different modules, boundaries, or concerns).
2. **Unblocking:** Prefer work that **unblocks** other backlog items or reduces risk for parallel work.
3. **Early value:** Among safe choices, prefer tasks that deliver **high value if completed soon**.

If no backlog task is suitable, do not write `__NEXT_TASK_FILE__` (leave it absent or empty).

## Output

Write **only** the single repo-relative path of the chosen task (one line, no markdown fences, no commentary) to **`__NEXT_TASK_FILE__`**.

The path must:
- exist on disk,
- be under `__TASKS_ROOT__/backlog/`,
- correspond to a task file that still has **pending** checklist items.
