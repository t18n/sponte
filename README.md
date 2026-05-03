# Sponte

Sponte is an orchestration layer for AFK (away-from-keyboard) agentic workflows: it drives unattended cycles that claim and run tasks from a workspace task store across multiple git workspaces.

The name is Latin *sponte*, meaning *of one’s own accord*.

The public package and CLI command are `sponte`.

I built Sponte because I wanted agents to pull work from a real task queue while I was away—without losing what was claimed, where it ran, how to resume after interruptions, or how to review changes before they landed on the trunk.

## Experimental status

Sponte is **experimental** and shaped around my personal workflow. It is **opinionated**, not plug-and-play automation, and the defaults assume you will tweak prompts, workspace settings, and task flow.

**Recommended:** run from a clone with [`uv`](https://docs.astral.sh/uv/) (`uv sync`, `uv run sponte …`) so you can adapt the repo to your stack instead of treating released wheels as a finished product.

### Sharp edges

- Expect to be comfortable with **git**, **worktrees**, and reading **diffs** before merges.
- Agent runs go through **native upstream harness CLIs** (Cursor, Claude, Codex, etc.); you install and authenticate those yourself.
- Sponte is intended for permissive local development workflows. It does **not** sandbox commands, file access, network access, secrets, or production resources.
- Use it only in development workspaces where you are comfortable giving the selected harness full command permissions. Do **not** run it against production environments or production credentials.
- Recovery paths and local state can be subtle when paths or machines differ; plan on occasional **`task-cleanup`** / inspection under `.sponte/jobs/`.

## Who this is for

You might reach for Sponte if you already keep work as a **markdown task backlog**, want **repeatable unattended passes** against explicit task files, and benefit from **isolated worktrees** plus **resume** after interrupted runs—especially on ongoing repos with recurring implementation or maintenance work. It is a poor fit for one-off scripts or tiny projects with no durable task queue.

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

For now, prefer the local `uv` flow above if you want to adapt prompts, settings, or task behavior for your own workflow.

## Core Commands

```bash
# Bootstrap Sponte inside the current git workspace
sponte init

# Create or refine task markdown in an initialized workspace
sponte task-plan --workspace /absolute/path/to/workspace

# Inspect resolved `.sponte/settings.json` defaults
sponte config show --workspace /absolute/path/to/workspace

# Override the workspace trunk branch for one run
sponte agent --workspace /absolute/path/to/workspace --trunk-branch main

# Start an agent cycle for one explicit task
sponte agent --workspace /absolute/path/to/workspace --task /absolute/path/to/workspace/.sponte/tasks/example-task.md

# Token rotation refresh stays in the same Sponte session automatically
# (no manual `session-resume` needed for the normal threshold handoff)
sponte agent --workspace /absolute/path/to/workspace --task /absolute/path/to/workspace/.sponte/tasks/example-task.md --rotate-threshold-tokens 80000

# Resume the same session (lane)
sponte session-resume rap-abcd1234 --workspace /absolute/path/to/workspace

# Resume an interrupted task in a new session
sponte task-resume my-task-abc123 --workspace /absolute/path/to/workspace

# Inspect task/session state (repo-local under `.sponte/jobs/`)
sponte status --workspace /absolute/path/to/workspace
sponte task-list --workspace /absolute/path/to/workspace
sponte task-current --workspace /absolute/path/to/workspace
sponte session-current --workspace /absolute/path/to/workspace

# Recover one orphaned worktree and exit
sponte agent --workspace /absolute/path/to/workspace --resume-task "<task_id from status or jobs>"

# Worktree maintenance
sponte worktree-prune-clean --workspace /absolute/path/to/workspace
sponte worktree-remove --workspace /absolute/path/to/workspace
```

**Documentation:** [docs/index.md](docs/index.md) (concepts, guides, CLI and config reference).

**Community and safety:** [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## Workspace Model

Workspace-owned files live under `workspace/.sponte/`:

- `.sponte/settings.json` stores workspace settings such as the default trunk branch and worktree root.
- `.sponte/guardrails.md` stores durable workspace guidance.
- `.sponte/tasks/` is the canonical task store.
- `.sponte/jobs/` holds a **repo-local** index of tasks and sessions (`tasks/<task_id>/`, `sessions/<session_id>/`) you can inspect with normal tools.
- `.sponte/worktrees/` is the default worktree root.

Git ignore rules:

- `sponte init` appends `.sponte/` to the workspace `.gitignore` so the whole Sponte directory stays untracked by default.
- If `worktree_root` is outside `.sponte/`, that path is appended as well.
- To version parts of `.sponte/` (for example settings or tasks), add them with `git add -f` or adjust `.gitignore`.

By default, cross-workspace runtime state lives outside the repo checkout:

- known workspace registry
- resume files
- locks (merge/selection/agent-pick; not `.sponte/locks/` task claims)
- logs
- rotation handoffs
- next-task files

Optional **workspace-local** runtime: set `"runtime_data": "workspace"` in `.sponte/settings.json` or export `SPONTE_RUNTIME_DATA_IN_WORKSPACE=1` to store that tree under `.sponte/runtime/` (alongside tasks and settings; still gitignored by default with `.sponte/`). Use `SPONTE_RUNTIME_DATA_IN_WORKSPACE=0` to force app state even when the file requests workspace mode.

Default app-state locations (when not using workspace-local runtime):

- macOS: `~/Library/Application Support/sponte`
- Linux/XDG: `$XDG_STATE_HOME/sponte` or `~/.local/state/sponte`
- override: `SPONTE_STATE_DIR`

Other environment variables:

- `SPONTE_RUNTIME_DATA_IN_WORKSPACE`: when truthy (`1`, `true`, `yes`), store Sponte runtime data under `.sponte/runtime/`; when `0`/`false`/`no`, force app state even if settings request workspace mode.
- `RALPH_VERIFY_COMMANDS`: `;;`-separated shell commands injected into verify-related agent prompts when `.sponte/settings.json` has no non-empty `commands.verify` list. Per-workspace `commands.verify` overrides this when set.

## Init Flow

`sponte init` is the workspace bootstrap entrypoint.

It will:

1. require that you run it inside a git checkout
2. optionally import tasks from an existing markdown file or folder
3. create `.sponte/tasks/`, `.sponte/settings.json`, and the default worktree root
4. set the default trunk branch to `sponte` unless you choose another name
5. ensure the local trunk branch exists
6. pre-fill `commands` in `.sponte/settings.json` when the repo root looks like a single stack (see [Configuration](docs/reference/config.md)); re-running `sponte init` on an existing workspace merges any new detections without overwriting values you already set

After initialization, use `sponte task-plan` to add or refine task markdown under `.sponte/tasks/` before starting the first `sponte agent` cycle.

## Planning Flow

`sponte task-plan` works only in an initialized workspace.

It will:

1. validate that `.sponte/tasks` already exists
2. prompt for one or more task titles, goals, and verification commands
3. write task markdown files under `.sponte/tasks/`
4. let `sponte agent --auto` choose among unlocked markdown tasks via the plan model
5. warn and continue to another task if a picked task hits a stale setup collision before resume state is persisted

## Recovery Flow

`sponte agent --resume-task <task_id>` uses saved Sponte runtime state for that task id, runs exactly one cycle (orphan worktree recovery), and then exits.

## Positioning

Sponte is a **local orchestration layer**: it coordinates markdown tasks, git worktrees, and **official harness CLIs** in headless mode. It is not an IDE, editor, or diff/review replacement. Use your normal editor, `git`, and diff tools to inspect `.sponte/jobs/` and worktrees.

Sponte intentionally does **not** embed a custom agent runtime, so it can track upstream harness changes and paid subscriptions (Cursor, Claude, Codex, etc.) without re‑implementing them.

## Safety and provider usage

Sponte drives native/official harness CLIs; it is not a provider-bypass layer or custom agent runtime. You should still expect normal provider billing, rate limits, authentication, and policy enforcement from whichever CLI you run.

The larger local risk is execution scope. Sponte is designed for fully permissive development loops and does not sandbox agent commands, file access, network access, secrets, or production resources. Prefer conservative defaults, avoid on-demand spending unless you accept that tradeoff, and review harness output and git diffs before merging.

## AI Rules

Sponte runs agent work from the target workspace and prompts agents to read workspace instruction files such as `AGENTS.md` and `CLAUDE.md` when present. Workspace-owned guidance in `.sponte/guardrails.md` complements those files; it does not replace them.

## Repo Layout

- core logic: `ralph_focus/`
- config defaults: `config/`
- prompt templates: `prompts/`
- tests: `tests/`


## Philosophy

Sponte is built around a simple idea: keep task state explicit under `.sponte/`, keep workspace rules close to the code, and let a harness run one focused unattended **session** at a time. It prefers Markdown task queues, isolated git worktrees, and resumable local state over hidden orchestration.

There is intentionally no built-in `--parallel N` mode. If you want multiple runs at once, start multiple `sponte agent` sessions from different terminals (use distinct `--runner-id` / `RALPH_RUNNER_ID` when needed). Cooperative locks coordinate shared-repo access without a daemon.

## Ralph Lineage

Sponte keeps the core Ralph workflow: pick a task, create or resume a worktree, run planner/executor-style phases, verify the result, and merge progress back into the workspace. In that sense it is very close to the original Ralph Wiggum-style loop.

What changed is the product layer around that core. Sponte makes the public CLI and package name explicit, centers the workspace model on `.sponte/`, supports multiple workspaces more directly, and treats task stores, guardrails, and workspace settings as Sponte-owned primitives. Internal Python modules still use `ralph_focus/` in places while that naming transition finishes.

## Maintainer: Publishing to PyPI

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
