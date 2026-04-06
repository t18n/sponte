# CLI reference (summary)

Run `sponte --help` and `sponte <command> --help` for the full Typer help.

## Workspace bootstrap

| Command | Purpose |
| --- | --- |
| `init` | Create `.sponte/` layout, settings, tasks dirs (interactive); pre-fills `commands` when detectable; on an existing workspace, merges detected commands into empty fields only |
| `task-plan` | Create or refine backlog markdown tasks |
| `config show` | Print effective `.sponte/settings.json` fields |

## Execution

| Command | Purpose |
| --- | --- |
| `agent` | Main loop: claim task, worktree, phases, merge (`session-resume` wraps `--resume-session`; `--task`, `--auto`, `--resume-task` for task selection / recovery). `--auto` picks a backlog task using the plan model and `prompts.agent_pick_task` (not `priorities.md`) |
| `session-resume SESSION_ID` | Resume an interrupted session by id |
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
| `session-show SESSION_ID` | Session job fields (key/value table) |
| `task-list` | Files under `.sponte/tasks/backlog/` |
| `task-priority` | `priorities.md` pending links + resolved `task_id` |
| `task-current` | Tasks with non-empty `owning_session_id` |
| `task-show TASK_ID` | Task job fields (key/value table) |
| `stats` | Machine-local analytics summary + recent JSONL events (tabular) |

## Worktrees

| Command | Purpose |
| --- | --- |
| `worktree-prune-clean` | Prune merged / unreferenced Sponte worktrees |
| `worktree-remove` | Interactive removal |

## Policy knobs (settings)

`.sponte/settings.json` `policy` section includes:

- `max_phase_rounds` (default 20): when an active task still has pending checklist items after that many counted agent phases, Sponte moves it to `review-required`, stops the loop for that task, and frees the claim so another session can pick it up via `task-resume`.
- `verification_required: false` skips the VERIFY phase.
- `merge_required: false` skips merging the feature branch into the trunk on the primary checkout after wrap/priorities; you merge manually. The worktree is still torn down and the session completes the task from Sponte’s perspective; local branch deletion may use `git branch -D` when the branch was never merged.

See [backpressure.md](../concepts/backpressure.md) and [config.md](config.md).
