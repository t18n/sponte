# Sponte

Sponte is a standalone CLI for unattended task cycles across multiple git workspaces. The name is Latin *sponte*, meaning *of one’s own accord*.

The public package and command are `sponte`.

## Install

### Local only (this computer, no PyPI)

You do not need PyPI or a release tag to use Sponte on one machine. From a clone of this repo:

Run inside the project (uses the repo virtualenv):

```bash
uv sync
uv run sponte --help
```

Install the `sponte` command globally for your user while you keep editing the repo (editable):

```bash
uv tool install --editable .
sponte --help
```

Install into the active environment from the source tree:

```bash
uv pip install .
```

Build a wheel and install that artifact (useful to mimic a release without uploading):

```bash
uv build
uv pip install dist/sponte-*.whl
```

### From PyPI

After a public release is published:

```bash
pip install sponte
# or
uv tool install sponte
```

## Publishing to PyPI

Releases are automated with GitHub Actions when you push a version tag. The workflow alone is not enough until PyPI trusts this repository.

### One-time setup

1. **Create the project on PyPI** (if it does not exist): the first successful upload to a name creates the project; see [PyPI help](https://pypi.org/help/) if you need to claim or transfer a name.
2. **Trusted Publisher**: In PyPI, open the `sponte` project → **Publishing** → **Add a new pending publisher** → choose **GitHub** and set:
   - Owner / repository: this GitHub repo
   - Workflow name: `publish.yml`
   - Environment name: `pypi` (must match the workflow’s `environment: pypi`)
3. **GitHub environment** (recommended): Create an environment named `pypi` in the repo settings. You can add protection rules (required reviewers) so tag pushes do not publish without approval.

See PyPI’s [Trusted Publishers](https://docs.pypi.org/trusted-publishers/) documentation for details.

### Release checklist

1. Bump `version` in `pyproject.toml` and merge to your release branch (e.g. `main`).
2. Run tests, e.g. `uv run pytest`.
3. Create and push an annotated tag whose version matches `pyproject.toml` (leading `v`):

   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin v0.1.0
   ```

The workflow [`.github/workflows/publish.yml`](.github/workflows/publish.yml) builds with `uv build` and fails if the tag (without `v`) does not equal `project.version` in `pyproject.toml`.

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


## Philosophy

Sponte is built around a simple idea: keep task state explicit, keep workspace rules close to the code, and let an agent run one focused unattended cycle at a time. It prefers Markdown task queues, isolated git worktrees, and resumable local state over hidden orchestration.

There is intentionally no built-in `--parallel N` mode. If you want multiple runs at once, start multiple `sponte` sessions from different terminals. That design keeps each run legible and recoverable as its own session, avoids hiding scheduler behavior behind one parent process, and lets cooperative locks handle shared repo coordination only where needed.

## Ralph Lineage

Sponte keeps the core Ralph workflow: pick a task, create or resume a worktree, run planner/executor-style phases, verify the result, and merge progress back into the workspace. In that sense it is very close to the original Ralph Wiggum-style loop.

What changed is the product layer around that core. Sponte makes the public CLI and package name explicit, centers the workspace model on `.sponte/`, supports multiple workspaces more directly, and treats task stores, guardrails, and workspace settings as Sponte-owned primitives. Internal Python modules still use `ralph_focus/` in places while that naming transition finishes.

## Best Fit

Sponte works best for software projects that already manage work as a backlog, want repeatable AI-assisted task execution, and benefit from isolated worktrees plus recovery after interrupted runs. It is strongest for ongoing engineering repos with recurring maintenance, implementation, or follow-up work, rather than one-off scripts or tiny projects with no durable task queue.
