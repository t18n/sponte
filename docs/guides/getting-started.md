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

`init` also tries to detect workspace lifecycle commands (`install`, `dev`, `check`, `build`, `test`, and an ordered `verify` list) from files at the repo root (for example `package.json`, `Cargo.toml`, `go.mod`, or Python/pytest hints). If several of those ecosystems are present at the root, Sponte skips guessing and leaves `commands` for you to set. Re-running `sponte init` later merges any new detections into **empty** fields without overwriting edits. You can always adjust `commands` in `.sponte/settings.json`. They act as a **token saver**: pointing Sponte at fast, repo-specific checks avoids generic or overly heavy verification and cuts down noisy command output in agent sessions.

## First tasks

```bash
sponte task-plan --workspace /path/to/repo
```

Add one or more backlog tasks. Optionally edit markdown under `.sponte/tasks/backlog/` directly.

## Run an agent session

```bash
sponte agent --workspace /path/to/repo --task /path/to/repo/.sponte/tasks/backlog/my-task.md
```

Or use `sponte agent --workspace /path/to/repo --auto` so Sponte picks the next pending task from `priorities.md` (requires an existing `.sponte/tasks/` tree). Use `sponte status` and `sponte task-current` to see ownership.

## Learn more

- [Tasks and sessions](../concepts/tasks-and-sessions.md)
- [CLI reference](../reference/cli.md)
- [Configuration](../reference/config.md)
