# Observability: status and stats

## Repo-local inspection

- **`sponte status`** — quick counts: active sessions/tasks from the job index, task-store size, hints for next commands.
- **`session-current`**, **`task-current`** — tables from `.sponte/jobs/*/status.json`.
- **`session-show`**, **`task-show`** — key/value panels for one id.
- **`task-list`** — markdown task files under `.sponte/tasks/` (excluding reserved helper subtrees).
- **`task-current`** — claimed tasks with absolute lock paths, owners, and worktrees.

## Machine-local stats

**`sponte stats`** always prints a **global** rollup from Sponte app state (no git workspace required):

- **`{SPONTE_STATE_DIR}/analytics/global_summary.json`** (default base is documented in the README) — counters mirrored from all workspaces: sessions started/resumed, tasks claimed/completed/cancelled/review-required, cleanup repairs, **total task wall time** (sum of per-completion `duration_sec`), **total API tokens** (sum of per-task deltas from claim to completion, using `total_token_count`), **lines added/deleted** (best-effort `git diff --numstat` at task completion), and **`updated_at`**. The CLI shows **registered workspaces** (paths in `known_workspaces.json`, updated when Sponte resolves a checkout root), not the internal path-hash list used while merging rollups (that list grows with every distinct **resolved** checkout path and can be large after temp clones, moved folders, or anything sharing your default state dir). It also shows **active agent sessions** by scanning `ralph.lock` files under `workspaces/*/ralph.lock` plus, for known workspaces using workspace-local runtime data, `.sponte/runtime/ralph.lock`, and counting locks whose **PID** still looks alive (stale locks are called out when any lock files exist).

When the current working directory is a Sponte workspace (or you pass **`-w` / `--workspace`**), a second panel shows **this workspace’s** `analytics/summary.json` under that workspace’s `ralph_data_dir` (app-state slug dir or `.sponte/runtime/`), plus **recent rows** from **`events.jsonl`** (`session_started`, `session_resumed`, `task_claimed`, `task_completed`, `task_review_required`, `task_cancelled`, `task_ownership_transferred`, `task_cleanup`, …). Event rows include **`duration_sec`**, **`cycles`**, and optional **`metadata`** (e.g. `token_delta`, `lines_added`, `lines_deleted` on `task_completed`).

Stats are **best-effort** and **append-only**; they are not the source of truth for active ownership (`.sponte` job status is). **Active session counts** can miss agents that only use workspace-local runtime and have never registered that checkout in `known_workspaces.json`.

## Logs and resume

Detailed run logs and `resume.state` live under app state in `runners/<session_id>/agent/` (new paths). Legacy `auto-focus/` resume files are still loaded if present.
