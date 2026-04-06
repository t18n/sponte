# Tasks and sessions

## Task

Tasks are markdown files anywhere under `.sponte/tasks/` (legacy staged paths such as `backlog/…` still work). Reserved subtrees `_tmp/` and `artifacts/` under tasks are excluded from selection.

Each task has a **`task_id`**: `t-` plus 16 hex characters derived from the **resolved absolute path** of the task file on disk. It stays stable while the file stays at that path; renaming or moving the file changes `task_id`.

**Path locks:** `.sponte/locks/tasks.lock` lists claimed tasks as newline-separated absolute paths. Claim also uses a per-task file under `.sponte/locks/tasks/`.

**Display names:** After claim, Sponte may run a short `task_display_name` prompt (override via `prompts.task_display_name` in settings) and store `display_name` / `ai_summary` in the task job `status.json`.

**Merged artifacts:** Sponte-created helper files can be listed under `artifacts` in job `status.json` and are copied into `.sponte/artifacts/tasks/<task_id>/` when a cycle completes successfully (that tree can be tracked in git; see root `.gitignore` rules).

## Session

A **session** is one Sponte invocation, identified by an id such as `rap-…`. That id is the resume handle (`session-resume`) and the directory name under `.sponte/jobs/sessions/<session_id>/`.

Sessions are **lanes**, not tasks: one session may run many tasks over time, one after another. At any moment, a session **owns at most one** active claimed task.

## Worktree

While a task is actively worked, Sponte uses a dedicated git worktree. The path is recorded in job metadata; **`task_id`** is the stable handle for `.sponte/jobs/tasks/<task_id>/`.

## Typical flow

1. Pending tasks (checklist items still open) are discoverable under `.sponte/tasks/`; `--auto` uses the plan model and `prompts.agent_pick_task` with lock-aware context.
2. `sponte agent` claims a task: computes `task_id`, takes the per-task lock, appends the primary’s absolute task path to `tasks.lock`, creates the worktree, and writes job rows under `.sponte/jobs/`. The task file is **not** moved to `in-progress` by default.
3. Phases run in the worktree (plan, implement, verify, merge to trunk by default). Merge serializes on the primary with both app-state branch locks and repo-local `.sponte/locks/merge.lock` (session id + configurable backoff in `merge_backoff_exponential`).
4. On success, the task file is removed from the primary branch (`git rm` when tracked), the path is removed from `tasks.lock`, and the per-task job directory is pruned unless `cleanup_pending` is set.
5. On `review-required` (policy: max phase rounds), the path is removed from `tasks.lock`, `review_required` is set in job status, and the claim is cleared so another session can use `task-resume`.

See [session-task-ownership.md](session-task-ownership.md) for resume semantics and [task-states.md](task-states.md) for the state machine.
