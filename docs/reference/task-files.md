# Task files and `task_id`

## Layout

Tasks are markdown files anywhere under `.sponte/tasks/`. Nested folders are allowed. Reserved subtrees such as `.sponte/tasks/_tmp/` and `.sponte/tasks/artifacts/` are not treated as tasks.

## `task_id` format

```
t-<16hex(path-hash)>
```

- `task_id` is derived from the task file's resolved absolute path.
- Renaming or moving the task file changes `task_id`.
- The human-facing label comes from AI naming or the markdown title; `task_id` stays machine-oriented.

## Selection

`sponte agent --auto` chooses among unlocked markdown task files under `.sponte/tasks/` using the workspace plan model and `prompts.agent_pick_task`. `tasks.lock` is the claim gate; `task-current` shows the current absolute lock paths and owners.

## Content

Task markdown does not need frontmatter, stage folders, or checklist syntax. A first `# Heading` is enough for a readable default label, but even that is optional.
