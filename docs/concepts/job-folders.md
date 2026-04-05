# Job folders under `.sponte/jobs/`

Sponte keeps a **dual index** so neither tasks nor sessions are nested only under the other:

- **`jobs/tasks/<task_id>/`** — task-centric files: `status.json`, `task.md`, `task.original.md`, `plan.md`, `improvements/`, `artifacts/`.
- **`jobs/sessions/<session_id>/`** — session-centric files: `status.json`, `logs/`, and per-task subfolders under `tasks/<task_id>/` when needed.

## Why this matters

Outputs stay **in the repository**, next to the code, diffable and inspectable with normal tools. Sponte is not a black-box remote control plane: the job layout is a deliberate product surface.

## Retention

Completed tasks keep history under `jobs/tasks/<task_id>/`. `task-cleanup` repairs inconsistencies; it does not delete healthy completed history by default. See the CLI help for `task-cleanup` when in doubt.
