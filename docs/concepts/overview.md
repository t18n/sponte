# Concepts overview

## Task

A unit of work described as a markdown file anywhere under `.sponte/tasks/`.

Each active task has a stable-for-that-path **`task_id`** derived from the resolved task file path (`t-<hex>`). Human-facing labels come from the markdown title or AI-generated `display_name`.

## Session

A **session** is one Sponte run, identified by an opaque id such as `rap-…`. A session is a long-lived *lane*: over time it may process many tasks sequentially, but it may **own at most one active task at a time**.

## Worktree

Git worktrees isolate agent edits from your primary checkout. Worktree paths are an implementation detail; **`task_id`** is the primary handle for job artifacts under `.sponte/jobs/tasks/<task_id>/`.

## Source of truth

- **Workspace (in the repo):** `.sponte/tasks/`, `.sponte/settings.json`, `.sponte/jobs/`, and `.sponte/locks/` own task lifecycle and active-claim metadata.
- **Machine (outside the repo):** Sponte app state holds resume files, cooperative locks, logs, and **analytics** used by `sponte stats`.

If machine-local resume data and repo-local job metadata disagree about ownership, prefer repairing toward `.sponte` (see `sponte task-cleanup`).

## Control vs inspection

- **Control:** `sponte agent`, `session-resume`, `task-resume`, `task-cancel`, `task-cancel-all`, `task-cleanup`
- **Inspection:** `status`, `session-current`, `session-show`, `task-list`, `task-current`, `task-show`, `stats`, `config show`

## Harnesses

Built-in harnesses map to official CLIs. **Custom** harnesses are thin: executable plus fixed arguments; the prompt is passed as the final argument and the current model is exposed as `SPONTE_MODEL` in the subprocess environment. Validate selections during `sponte init`.

## More reading

- [Tasks and sessions](tasks-and-sessions.md), [ownership](session-task-ownership.md), [state model](state-model.md)
- [Job folders](job-folders.md), [task states](task-states.md), [backpressure](backpressure.md)
- [Guides: getting started](../guides/getting-started.md), [provider safety](../guides/provider-safety.md)
