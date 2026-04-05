# Tasks and sessions

## Task

Tasks are markdown files under `.sponte/tasks/`, organized by stage (`backlog`, `in-progress`, `review-required`, `completed`). Each task has a **`task_id`**: a slug from the filename stem plus a six-character hash of the **task title** only. If you change the title, the `task_id` changes.

## Session

A **session** is one Sponte invocation, identified by an id such as `rap-…`. That id is the resume handle (`session-resume`) and the directory name under `.sponte/jobs/sessions/<session_id>/`.

Sessions are **lanes**, not tasks: one session may run many tasks over time, one after another. At any moment, a session **owns at most one** active claimed task.

## Worktree

While a task is actively worked, Sponte uses a dedicated git worktree. The path is recorded in job metadata; **`task_id`** is the stable handle for `.sponte/jobs/tasks/<task_id>/`.

## Typical flow

1. Backlog tasks live under `.sponte/tasks/backlog/`.
2. `sponte agent` claims a task: generates or reuses `task_id`, takes a lock under `.sponte/locks/`, moves the task file to `in-progress`, creates the worktree, and writes job rows under `.sponte/jobs/`.
3. Phases run in the worktree (plan, implement, verify, merge to trunk by default).
4. On success, the task moves to `completed` and the worktree is removed.
5. On `review-required` (policy: max phase rounds), the task moves to `review-required` and the claim is cleared so another session can pick it up with `task-resume`.

See [session-task-ownership.md](session-task-ownership.md) for resume semantics and [task-states.md](task-states.md) for the state machine.
