# Observability: status and stats

## Repo-local inspection

- **`sponte status`** — quick counts: active sessions/tasks from the job index, task-store size, hints for next commands.
- **`session-current`**, **`task-current`** — tables from `.sponte/jobs/*/status.json`.
- **`session-show`**, **`task-show`** — key/value panels for one id.
- **`task-list`** — markdown task files under `.sponte/tasks/` (excluding reserved helper subtrees).
- **`task-current`** — claimed tasks with absolute lock paths, owners, and worktrees.

## Machine-local stats

**`sponte stats`** always prints a **global** rollup from Sponte app state (no git workspace required):

- **`{SPONTE_STATE_DIR}/analytics/global_summary.json`** (default base is documented in the README) — counters mirrored from all workspaces: sessions started/resumed, tasks claimed/completed/cancelled/review-required, cleanup repairs, **total task wall time** (sum of per-completion `duration_sec`), **total API tokens** (sum of per-task deltas from claim to completion, using `total_token_count`), **lines added/deleted** (best-effort `git diff --numstat` at task completion), and **`updated_at`**. The CLI shows **registered workspaces** (paths in `known_workspaces.json`, updated when Sponte resolves a checkout root), not the internal path-hash list used while merging rollups (that list grows with every distinct **resolved** checkout path and can be large after temp clones, moved folders, or anything sharing your default state dir). It also shows **active agent sessions (machine-wide)** by scanning `ralph.lock` files under `workspaces/*/ralph.lock` plus, for known workspaces using workspace-local runtime data, `.sponte/runtime/ralph.lock`, and counting locks whose **PID** still looks alive (stale locks are called out when any lock files exist).

When the current working directory is a Sponte workspace (or you pass **`-w` / `--workspace`**), a second panel shows **this workspace’s** `analytics/summary.json` under that workspace’s `ralph_data_dir` (app-state slug dir or `.sponte/runtime/`), plus **recent rows** from **`events.jsonl`** (`session_started`, `session_resumed`, `task_claimed`, `task_completed`, `task_review_required`, `task_cancelled`, `task_ownership_transferred`, `task_cleanup`, …). Event rows include **`duration_sec`**, **`cycles`**, and optional **`metadata`** (e.g. `token_delta`, `lines_added`, `lines_deleted` on `task_completed`). In that panel, **Session active now** counts only this checkout’s `ralph.lock` under the same `ralph_data_dir` (0 or 1 while a single lock file is shared per primary).

**Interpreting zeros:** **Task finished**, **total wall time**, **lines**, **merges**, and **token** rollups update only after a task completes the full success path (merge/worktree cleanup as configured). Aborted sessions or stuck tasks leave those counters unchanged. **Token** totals depend on the harness reporting usage (e.g. Cursor fills usage when stream JSON is enabled); otherwise per-task token deltas may stay zero even on completion. **Per-workspace** summaries always live under `ralph_data_dir` for the resolved primary; if `runtime_data` / `SPONTE_RUNTIME_DATA_IN_WORKSPACE` or the checkout path differs between runs, the second panel can look empty while the global rollup still reflects other paths.

Stats are **best-effort** and **append-only**; they are not the source of truth for active ownership (`.sponte` job status is). **Global** active session counts can miss agents that only use workspace-local runtime and have never registered that checkout in `known_workspaces.json`.

Live session counts use PID liveness probes from `ralph.lock`, so they can be wrong in edge cases such as PID reuse after a process exits. Treat them as a convenience signal, not an ownership lock.

## Logs and resume

Detailed run logs and `resume.state` live under app state in `runners/<session_id>/agent/` (new paths). Legacy `auto-focus/` resume files are still loaded if present.
