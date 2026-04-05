# Observability: status and stats

## Repo-local inspection

- **`sponte status`** — quick counts: active sessions/tasks from the job index, backlog size, hints for next commands.
- **`session-current`**, **`task-current`** — tables from `.sponte/jobs/*/status.json`.
- **`session-show`**, **`task-show`** — key/value panels for one id.
- **`task-list`**, **`task-priority`** — backlog files and `priorities.md` with resolved `task_id`s.

## Machine-local stats

**`sponte stats`** reads:

- **`summary.json`** — cheap counters: sessions started/resumed, tasks completed, cancelled, `review-required`, cleanup repairs, and a timestamp.
- **`events.jsonl`** — one JSON object per line for recent history (session start, resume, task completed, cancelled, ownership transfer, cleanup, etc.).

Stats are **best-effort** and **append-only**; they are not the source of truth for active ownership (`.sponte` is).

## Logs and resume

Detailed run logs and `resume.state` live under app state in `runners/<session_id>/agent/` (new paths). Legacy `auto-focus/` resume files are still loaded if present.
