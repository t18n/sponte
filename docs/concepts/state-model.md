# State model: repo vs machine

## Workspace-owned (in the repo)

Under `.sponte/`:

- **`tasks/`** — task markdown by stage.
- **`settings.json`** — harness, models, prompts map, guardrails path, policy knobs.
- **`jobs/`** — durable index: `jobs/tasks/<task_id>/` and `jobs/sessions/<session_id>/` (status, snapshots, artifacts).
- **`locks/`** — cooperative claim locks keyed by `task_id`.

This is what `status`, `task-current`, `session-current`, and related commands read first.

## Machine-local app state (default)

Outside the checkout (see `SPONTE_STATE_DIR` in the README), Sponte keeps a per-workspace directory keyed by a hash of the resolved workspace root:

- Per-workspace **resume** files and **logs** under `…/workspaces/<slug>/runners/<session>/agent/` (legacy: `auto-focus/` is still read for old resume files).
- **Cooperative locks** for merge and selection that are not workspace task ownership.
- **Analytics**: `analytics/summary.json` counters and `analytics/events.jsonl` append-only events for `sponte stats`.

## Optional workspace-local runtime

If `.sponte/settings.json` sets `"runtime_data": "workspace"` or the environment sets `SPONTE_RUNTIME_DATA_IN_WORKSPACE` to a truthy value, the same runtime tree (resume, logs, plans, merge/selection locks, analytics, etc.) lives under **`.sponte/runtime/`** in the checkout instead of app state (still usually gitignored with `.sponte/`). `SPONTE_RUNTIME_DATA_IN_WORKSPACE=0` forces app state regardless of the file.

## Disagreements

If resume or lock files disagree with `.sponte/jobs/` about ownership, **repair toward `.sponte`**. Use `task-cleanup` for conservative fixes; use `task-cancel` when you intend to abandon an active task.
