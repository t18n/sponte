# Sponte

Sponte is a standalone CLI for unattended task cycles across multiple git workspaces.

The public package and command are `sponte`. Internal module names still use older identifiers in places, but workspace behavior is now Sponte-owned.

## Install

For local development in this repo:

```bash
uv sync
uv run sponte --help
```

To run `sponte` from anywhere on your machine during development:

```bash
uv tool install --editable .
sponte --help
```

## Core Commands

```bash
# Initialize or refresh a workspace task store
sponte plan --workspace /absolute/path/to/workspace

# Start an auto-focus cycle from anywhere
sponte auto-focus --workspace /absolute/path/to/workspace

# Override the workspace trunk branch for one run
sponte auto-focus --workspace /absolute/path/to/workspace --trunk-branch main

# Recover one orphaned worktree and exit
sponte auto-focus --workspace /absolute/path/to/workspace --complete-worktree "/absolute/path/to/workspace/.sponte/worktrees/raf-example-1234"

# Interactive menu
sponte interactive --workspace /absolute/path/to/workspace

# Worktree maintenance
sponte worktree-prune-clean --workspace /absolute/path/to/workspace
sponte worktree-remove --workspace /absolute/path/to/workspace
```

## Workspace Model

Workspace-owned files live under `workspace/.sponte/`:

- `.sponte/settings.json` stores workspace settings such as the default trunk branch.
- `.sponte/guardrails.md` stores durable workspace guidance.
- `.sponte/tasks/` is the canonical task store.
- `.sponte/worktrees/` is the canonical worktree root.

Git ignore rules:

- `.sponte/worktrees/` should be gitignored.
- `.sponte/tasks/` and tracked workspace settings should remain versioned.
- `sponte plan` updates the workspace `.gitignore` automatically when it initializes a workspace.

Cross-workspace runtime state lives outside the repo checkout:

- known workspace registry
- resume files
- locks
- logs
- rotation handoffs
- next-task files

Default app-state locations:

- macOS: `~/Library/Application Support/sponte`
- Linux/XDG: `$XDG_STATE_HOME/sponte` or `~/.local/state/sponte`
- override: `SPONTE_STATE_DIR`

## Init Flow

`sponte plan` is the workspace/task-generation entrypoint.

It will:

1. resolve the target workspace from `--workspace`, the current checkout, or the known-workspace registry
2. prompt for a source markdown file or folder when `.sponte/tasks` is missing or invalid
3. create `.sponte/tasks/`, `.sponte/worktrees/`, and `.sponte/settings.json`
4. set the default trunk branch to `sponte` unless overridden
5. ensure the local trunk branch exists

After initializing a new task store, review and commit the generated `.sponte/tasks` files before starting the first `auto-focus` cycle.

## Recovery Flow

`sponte auto-focus --complete-worktree <path>` uses saved Sponte runtime state to recover an orphaned worktree, resume exactly one cycle for that worktree, and then exit.

The interactive menu exposes the same recovery flow and can list recoverable worktrees by number.

## AI Rules

Sponte runs agent work from the target workspace and prompts agents to read workspace instruction files such as `AGENTS.md` and `CLAUDE.md` when present. Workspace-owned guidance in `.sponte/guardrails.md` complements those files; it does not replace them.

## Repo Layout

- core logic: `ralph_focus/`
- config defaults: `config/`
- prompt templates: `prompts/`
- tests: `tests/`
