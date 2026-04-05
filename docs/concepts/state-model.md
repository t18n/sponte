# State model: repo vs machine

## Workspace-owned (in the repo)

Under `.sponte/`:

- **`tasks/`** — task markdown by stage.
- **`settings.json`** — harness, models, prompts map, guardrails path, policy knobs.
- **`jobs/`** — durable index: `jobs/tasks/<task_id>/` and `jobs/sessions/<session_id>/` (status, snapshots, artifacts).
- **`locks/`** — cooperative claim locks keyed by `task_id`.

This is what `status`, `task-current`, `session-current`, and related commands read first.

## Machine-local app state

Outside the checkout (see `SPONTE_STATE_DIR` in the README):

- Per-workspace **resume** files and **logs** under `…/workspaces/<slug>/runners/<session>/agent/` (legacy: `auto-focus/` is still read for old resume files).
- **Cooperative locks** for merge and selection that are not workspace task ownership.
- **Analytics**: `analytics/summary.json` counters and `analytics/events.jsonl` append-only events for `sponte stats`.

## Disagreements

If resume or lock files disagree with `.sponte/jobs/` about ownership, **repair toward `.sponte`**. Use `task-cleanup` for conservative fixes; use `task-cancel` when you intend to abandon an active task.
