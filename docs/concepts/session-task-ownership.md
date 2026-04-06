# Session and task ownership

## Invariants

- One **active** task has exactly one **owning** session and one active worktree.
- One session owns **at most one** active task at a time.
- One session may process **many** tasks sequentially over its lifetime.
- A task may appear in **many** sessions historically; only **one** session may actively own it now.
- **`.sponte` is the source of truth** for workspace task ownership. Machine-local app state is not authoritative for “who owns this task?”

## `session-resume` vs `task-resume`

- **`session-resume <session_id>`** continues the **same lane** on whatever that session was doing (same runner id, same resume file under app state).
- **`task-resume <task_id>`** starts a **new** session id and **transfers** active ownership of that task into the new lane, using the existing worktree and saved phase when possible.

Use `task-resume` when you want a fresh session id but the same interrupted or `review-required` task. Use `session-resume` when you want to pick up exactly where a known session left off.

Token-rotation threshold refresh is different: Sponte keeps the same session id and, for built-in harnesses, starts the next agent invocation with fresh harness context automatically inside the same `sponte agent` loop. That path does **not** require `session-resume`.

## Cancellation

`task-cancel` is **destructive**: it clears locks and resume state for the owner, removes the worktree (even if dirty), and moves the task file from `in-progress` back to `backlog` when applicable so the task can be claimed again.

## Cleanup

`task-cleanup` is an **explicit repair** command. Normal commands should not silently fix unrelated stale state. Run it when you suspect orphan locks or job rows pointing at missing worktrees, stale `tasks.lock` lines for deleted files, or a **completed** task whose job directory was left behind with `cleanup_pending`. Use `--migrate-task-ids` once when upgrading from legacy title-based job folder names to path-derived ids (only when the task file still exists at `rel_task`).
