# Task display name

You label a Sponte task for the UI. Read the excerpt below (from the task file).

Write **exactly one line** of JSON to the file at `__NAMING_REPLY_PATH__` (create parent dirs if needed). No markdown fences.

Schema (plain text values, single line each):

```json
{"display_name":"…","ai_summary":"…"}
```

Rules:

- `display_name`: max 60 characters, short human title.
- `ai_summary`: max 160 characters, one sentence on intent/outcome.
- ASCII or Unicode text only; no newlines inside values.

## Task excerpt

__TASK_BODY_EXCERPT__
