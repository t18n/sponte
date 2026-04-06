# Observability: status and stats

## Repo-local inspection

- **`sponte status`** — quick counts: active sessions/tasks from the job index, backlog size, hints for next commands.
- **`session-current`**, **`task-current`** — tables from `.sponte/jobs/*/status.json`.
- **`session-show`**, **`task-show`** — key/value panels for one id.
- **`task-list`**, **`task-priority`** — backlog files and `priorities.md` links with resolved `task_id`s (human-facing index; `sponte agent --auto` does not order work from this file).

## Machine-local stats

**`sponte stats`** reads:

- **`summary.json`** — cheap counters: sessions started/resumed, tasks completed, cancelled, `review-required`, cleanup repairs, and a timestamp.
- **`events.jsonl`** — one JSON object per line for recent history (`session_started`, `session_resumed`, `task_claimed`, `task_completed`, `task_review_required`, `task_cancelled`, `task_ownership_transferred`, `task_cleanup`, …). Rows include top-level **`duration_sec`** and **`cycles`** (agent steps or phase-round context) when meaningful, plus **`harness`** / **`plan_model`** / **`execute_model`** when known.

Stats are **best-effort** and **append-only**; they are not the source of truth for active ownership (`.sponte` is).

## Logs and resume

Detailed run logs and `resume.state` live under app state in `runners/<session_id>/agent/` (new paths). Legacy `auto-focus/` resume files are still loaded if present.
