# Task states

Task files stay in the flat `.sponte/tasks/` store. State lives in `.sponte/jobs/tasks/<task_id>/status.json`, not in the task path.

## Lifecycle states

- **Unclaimed** — markdown file exists under `.sponte/tasks/` and its path is not present in `tasks.lock`.
- **In progress** — task path is locked, a session owns it, and Sponte has a worktree/job row for the task.
- **Review required** — the task was not marked complete before `max_phase_rounds`; claim is cleared, worktree may remain for inspection, and another session can take over with `task-resume`.
- **Completed** — merge/archive flow succeeded enough to mark `completed=true`; Sponte removes the task markdown from the flat store and later prunes the job dir unless `cleanup_pending=true`.

## Cancelled vs cleaned

- **Cancelled** — user ran `task-cancel`; claim reversed, worktree removed, and the markdown task stays available in the flat store.
- **Cleanup-repaired** — `task-cleanup` fixed orphan metadata (for example a locked task with no worktree or a deferred completed-job prune).

## `review-required` is not failure

It is a **handoff** state: spending stops for that task until a human reviews the worktree and job status, then you explicitly resume. It is **not** a blocking review gate inside the agent loop (v1 does not block the whole workspace on manual approval).
