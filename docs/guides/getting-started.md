# Getting started

## Prerequisites

- Git checkout of your project
- A harness CLI installed (e.g. Cursor, Claude Code, Codex) if you use a built-in harness
- Python + `uv` (see repository README) to run `sponte` from source, or install from PyPI when available

## Bootstrap

```bash
cd /path/to/repo
sponte init
```

`init` creates `.sponte/`, writes `.sponte/settings.json` after **validated** harness and model choices (lightweight probe such as `hello`), and sets up task directories.

## First tasks

```bash
sponte task-plan --workspace /path/to/repo
```

Add one or more backlog tasks. Optionally edit markdown under `.sponte/tasks/backlog/` directly.

## Run an agent session

```bash
sponte agent --workspace /path/to/repo .sponte/tasks/backlog/my-task.md
```

Or let the session pick from priorities when configured. Use `sponte status` and `sponte task-current` to see ownership.

## Learn more

- [Tasks and sessions](../concepts/tasks-and-sessions.md)
- [CLI reference](../reference/cli.md)
- [Configuration](../reference/config.md)
