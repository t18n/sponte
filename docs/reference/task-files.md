# Task files and `task_id`

## Layout

Tasks are markdown files under `.sponte/tasks/<stage>/`. The **filename stem** is part of identity; the **title** inside the file (first heading or front matter as implemented in `task_label`) feeds the hash.

## `task_id` format

```
<slugified-task-name>-<6charhash(task-title)>
```

- **Slugified name** comes from the file stem.
- **Six-character hash** is derived from the **task title only** (not the body). Changing the title changes `task_id`.

Use `sponte task-priority` to see `priorities.md` links with resolved ids (optional index).

**Auto selection:** `sponte agent --auto` chooses among pending **backlog** tasks using the workspace **plan model** and the `agent_pick_task` prompt (override with `prompts.agent_pick_task` in `.sponte/settings.json`). It considers claimed tasks in `.sponte/jobs/tasks/` so parallel sessions can steer away from in-flight work.

## Checklist

Sponte uses checklist items in the markdown to decide whether work is still **pending** for `review-required` and similar logic. Keep checklists explicit so phases and policy behave predictably.
