# CLI reference (summary)

Run `sponte --help` and `sponte <command> --help` for the full Typer help.

## Workspace bootstrap

| Command | Purpose |
| --- | --- |
| `init` | Create `.sponte/` layout, settings, and the flat task store (interactive); pre-fills `commands` when detectable; on an existing workspace, merges detected commands into empty fields only |
| `task-plan` | Create or refine markdown task files under `.sponte/tasks/` |
| `config show` | Print effective `.sponte/settings.json` fields |

## Execution

| Command | Purpose |
| --- | --- |
| `agent` | Main loop: claim task, worktree, phases, merge (`session-resume` wraps `--resume-session`; `--task`, `--auto`, `--resume-task` for task selection / recovery). Token-rotation threshold refresh stays inside the same loop for built-in harnesses, so normal context refresh does not require `session-resume`. `--auto` picks among unlocked markdown tasks under `.sponte/tasks/` using the plan model and `prompts.agent_pick_task`. If the CLI leaves a worktree behind, it prints `session-resume` only when a valid resume file exists; otherwise it points at `task-resume` / `task-current` |
| `session-resume SESSION_ID` | Resume an interrupted session by id; prints a one-line reason if nothing can be loaded (e.g. `missing_file`, `primary_mismatch`) |
| `task-resume TASK_ID` | New session id; rewrites resume for existing worktree + task |

## Lifecycle / repair

| Command | Purpose |
| --- | --- |
| `task-cancel TASK_ID` | Destructive: drop worktree, clear locks/resume for owner, and release the claimed markdown task back to the flat task store |
| `task-cancel-all` | Cancel every active task found under `.sponte/jobs/tasks/` |
| `task-cleanup` | Prune stale `tasks.lock` lines, retry deferred completed job-dir removal (`cleanup_pending`), and repair orphan task/session metadata; optional `--migrate-task-ids` renames legacy job dirs to path-derived ids |

## Inspection

| Command | Purpose |
| --- | --- |
| `status` | Short counts + suggested next commands |
| `session-current` | Sessions with a non-empty `active_task_id` in job `status.json` |
| `session-show SESSION_ID` | Session job fields (key/value table) |
| `task-list` | Markdown tasks under `.sponte/tasks/` (excludes `_tmp/`, `artifacts/`) |
| `task-current` | Claimed tasks with absolute lock paths, owning session, display name, and worktree |
| `task-show TASK_ID` | Task job fields (key/value table) |
| `stats` | Machine-local analytics summary + recent JSONL events (tabular) |

## Worktrees

| Command | Purpose |
| --- | --- |
| `worktree-prune-clean` | Prune merged / unreferenced Sponte worktrees |
| `worktree-remove` | Interactive removal |

## Policy knobs (settings)

`.sponte/settings.json` `policy` section includes:

- `max_phase_rounds` (default 20): when an active task is still not complete after that many counted agent phases in a single run/resume slice, Sponte marks it `review-required`, stops the loop for that task, and frees the claim so another session can pick it up via `task-resume`. `status.json` `completed=true` is the primary signal; legacy checklist-only tasks still fall back to checklist state.
- `verification_required: false` skips the VERIFY phase.
- `merge_required: false` skips merging the feature branch into the trunk on the primary checkout after wrap/verify; you merge manually. The worktree is still torn down and the session completes the task from Sponte’s perspective; local branch deletion may use `git branch -D` when the branch was never merged.

See [backpressure.md](../concepts/backpressure.md) and [config.md](config.md).
