# Backpressure and policy

Sponte exposes a small **policy** block in `.sponte/settings.json` so completion behavior is explicit instead of scattered implicit checks.

## Knobs (v1)

- **`max_phase_rounds`** — counted agent phases (plan/implement/improve/verify-like steps) per task. When the limit is hit and the checklist still has pending items, the task moves to **`review-required`** and the current loop stops **for that task** so another task can run.
- **`verification_required`** — when `false`, the VERIFY phase is skipped and the cycle moves toward merge (or completion) without running the verify prompt.
- **`merge_required`** — when `false`, Sponte **does not** merge the feature branch into the trunk on the primary checkout after the wrap/priorities path. The worktree is still removed and the local feature branch may be deleted with `git branch -D` if it was never merged; **you** merge to trunk when ready. When `true` (default), Sponte performs the usual merge into the configured trunk after checks.

## What “blocked” means

Inspection commands (`status`, `task-show`, `session-show`) surface phase and paths so you can see **where** work stopped. Human review is **not** a hard gate in v1: `review-required` is the explicit “stop spending loops here” outcome.

See [review-required.md](../guides/review-required.md) for operational guidance.
