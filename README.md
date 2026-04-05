# Sponte

Sponte is the standalone CLI product for unattended task execution cycles, powered by the existing Ralph core.

In this bootstrap slice, the public package and CLI are `sponte`, while the internal Python modules and repo data layout stay Ralph-oriented to reduce migration churn.

## Install

```bash
uv sync
```

## Use

```bash
uv run sponte --help
uv run sponte auto-focus --help
uv run sponte smoke
```

## What Sponte Boots With

- Ralph core under `ralph_focus/`
- config and command templates under `config/`
- prompt templates under `prompts/`
- pytest coverage for resume, rotation, CLI, progress, and task helpers under `tests/`

## Notes

- The public CLI is `sponte`.
- Internal repo state still lives under `.agents/ralph/` in this bootstrap phase.
- Task files still live under `.agents/tasks/`.
- Existing rotation handoff and resume behavior is intentionally preserved.
