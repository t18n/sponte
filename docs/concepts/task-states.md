# Task states

## Stages (file location)

- **`backlog`** — `.sponte/tasks/backlog/*.md`, ready to be claimed.
- **`in-progress`** — actively owned by a session; file usually updated in the worktree and synced via git operations Sponte performs.
- **`review-required`** — checklist still pending after **max phase rounds** (policy); not the same as **completed** or **cancelled**. Resume explicitly with `task-resume` (or continue the lane if your workflow still has a valid session).
- **`completed`** — done; forward transition from a successful cycle.

## Cancelled vs cleaned

- **Cancelled** — user ran `task-cancel`; claim reversed, worktree removed, task returned toward backlog when applicable.
- **Cleanup-repaired** — `task-cleanup` fixed orphan metadata (e.g. `in-progress` with no worktree); task may return to **backlog** when the tool determines work was not actually finished.

## `review-required` is not failure

It is a **handoff** state: spending stops for that task until a human reviews the worktree and checklist, then you explicitly resume. It is **not** a blocking review gate inside the agent loop (v1 does not block the whole workspace on manual approval).
