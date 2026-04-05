# Task files and `task_id`

## Layout

Tasks are markdown files under `.sponte/tasks/<stage>/`. The **filename stem** is part of identity; the **title** inside the file (first heading or front matter as implemented in `task_label`) feeds the hash.

## `task_id` format

```
<slugified-task-name>-<6charhash(task-title)>
```

- **Slugified name** comes from the file stem.
- **Six-character hash** is derived from the **task title only** (not the body). Changing the title changes `task_id`.

Use `sponte task-priority` to see backlog paths with resolved ids.

## Checklist

Sponte uses checklist items in the markdown to decide whether work is still **pending** for `review-required` and similar logic. Keep checklists explicit so phases and policy behave predictably.
