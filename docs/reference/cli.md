# CLI reference (summary)

Run `sponte --help` and `sponte <command> --help` for the full Typer help.

## Workspace bootstrap

| Command | Purpose |
| --- | --- |
| `init` | Create `.sponte/` layout, settings, tasks dirs (interactive) |
| `task-plan` | Create or refine backlog markdown tasks |
| `config show` | Print effective `.sponte/settings.json` fields |

## Execution

| Command | Purpose |
| --- | --- |
| `agent` | Main loop: claim task, worktree, phases, merge (same flags as legacy flow; use `--resume`, `--complete-worktree`, etc.) |
| `session-resume SESSION_ID` | Same as `agent --resume SESSION_ID` |
| `task-resume TASK_ID` | New session id; rewrites resume for existing worktree + task |

## Lifecycle / repair

| Command | Purpose |
| --- | --- |
| `task-cancel TASK_ID` | Destructive: drop worktree, clear locks/resume for owner, move primary task file from `in-progress` → `backlog` when present |
| `task-cancel-all` | Cancel every active task found under `.sponte/jobs/tasks/` |
| `task-cleanup` | Conservative repair of stale locks and orphan `in-progress` rows when the worktree is gone |

## Inspection

| Command | Purpose |
| --- | --- |
| `status` | Short counts + suggested next commands |
| `session-current` | Sessions with a non-empty `active_task_id` in job `status.json` |
| `session-show SESSION_ID` | One session job row |
| `task-list` | Files under `.sponte/tasks/backlog/` |
| `task-priority` | `priorities.md` pending links + resolved `task_id` |
| `task-current` | Tasks with non-empty `owning_session_id` |
| `task-show TASK_ID` | One task job row |
| `stats` | Machine-local analytics summary + recent JSONL events |

## Worktrees

| Command | Purpose |
| --- | --- |
| `worktree-prune-clean` | Prune merged / unreferenced Sponte worktrees |
| `worktree-remove` | Interactive removal |

## Policy knobs (settings)

`.sponte/settings.json` `policy` section includes `max_phase_rounds` (default 20). When an active task still has pending checklist items after that many counted agent phases, Sponte moves it to `review-required`, stops the loop for that task, and frees the claim so another session can pick it up via `task-resume`. `verification_required: false` skips the VERIFY phase.
