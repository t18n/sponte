# Migrating from `auto-focus` / `plan`

The CLI was renamed **without** compatibility aliases:

| Old | New |
| --- | --- |
| `sponte auto-focus` | `sponte agent` |
| `sponte plan` | `sponte task-plan` |

Mental model changes:

- Prefer **`task_id`** and **session id** (`rap-…`) over ad hoc worktree recovery.
- Repo-local **`.sponte/jobs/`** is the inspection surface for tasks and sessions.

Resume paths on disk moved from `runners/<id>/auto-focus/` to **`runners/<id>/agent/`**. Sponte still **reads** `auto-focus/resume.state` if the new path is missing so existing installs keep working; new writes use `agent/`.

Flags such as `--resume` / `session-resume` behave like before, but documentation and hints use session/task language.
