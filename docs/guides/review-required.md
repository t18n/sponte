# When a task is `review-required`

## What triggered it

The workspace policy **`max_phase_rounds`** (default 20) limits how many **counted agent phases** run in a single task run/resume slice while the task checklist still has pending items. When the limit is reached, Sponte:

- moves the task to **`review-required`**
- clears exclusive claim so another session can take work
- stops spending more agent loops on **that** task (other tasks can still run in other sessions)

## What to inspect

- The **worktree** path from `task-show <task_id>` or `session-show` history
- **Checklist** state in the task markdown
- **`.sponte/jobs/tasks/<task_id>/`** for snapshots and logs

## Resuming

Use **`task-resume <task_id>`** to attach a **new** session id to the existing worktree and continue, or **`session-resume`** if you are continuing the **same** lane that still owns the task (less common once claim is cleared).

This is **not** the same as “task failed”; it is an explicit handoff state so you do not burn tokens indefinitely on a stuck checklist.
