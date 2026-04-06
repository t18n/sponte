# Sponte Agent Notes

- Use `sponte` for the public CLI/package name. Internal Python modules still live under `ralph_focus/`.
- Prefer `uv run pytest` for verification. Run focused tests while iterating, then the full suite before claiming completion.
- Workspace-aware commands should usually be run with `--workspace /abs/path/to/workspace`.
- In a target workspace, files under `.sponte/` are workspace-owned. Runtime state such as locks, logs, resume files, and handoffs lives outside the repo in Sponte app state.
- If the target workspace has its own instructions, including `AGENTS.md`, `CLAUDE.md`, or `.sponte/guardrails.md`, follow that workspace guidance instead. Treat this file as repo-level guidance for developing Sponte itself.

## Learned User Preferences

- When the user wants git history split up, use several logical commits rather than one monolithic commit when the diff clearly separates concerns.
- Commits: keep the subject line to 50 characters or fewer total (including any `type(scope):` prefix); follow Conventional Commits as enforced by commitlint; use imperative mood; omit the body unless something critical needs explaining (wrap prose at about 72 characters per line if present); do not add AI or marketing footers or tool `Co-authored-by` unless the user asked for shared authorship.
- In CLI help output, show a short description beside each command name (top-level and subcommands).

## Learned Workspace Facts

- PyPI: push tag `v*` whose version (without `v`) matches `project.version` in `pyproject.toml`; `.github/workflows/publish.yml` builds with `uv build` and publishes via Trusted Publisher using GitHub environment `pypi` (one-time setup in README).
- Cross-workspace app state paths and `SPONTE_STATE_DIR` are documented in README; on macOS the default base is under `~/Library/Application Support/sponte`.
- Set `SPONTE_INIT_SKIP_HARNESS_PROBE=1` to skip harness and model probing during `sponte init` (e.g. tests or offline runs).
- Git worktrees default under `.sponte/worktrees`; override with `worktree_root` in `.sponte/settings.json`.
- Per-session resume and logs under app state use `runners/<id>/agent/`; legacy `auto-focus/` is still read for resume when the new path is absent.
- Token rotation should refresh agent chat context inside the same Sponte session/loop; routine rotation should not require or suggest `sponte session-resume`.
- Workspace `.sponte/settings.json` supports lifecycle `commands` (`install`, `dev`, `check`, `build`, `test`, `verify`); `sponte init` auto-detects defaults and docs position them as a token saver.
- `sponte init` should add `.sponte/` to `.gitignore` before other init work; if `worktree_root` is outside `.sponte/`, ignore that path too.
- `agent --auto` should choose among unlocked markdown files anywhere under `.sponte/tasks/`; do not rely on `priorities.md` or staged task folders.
- `sponte agent` uses `--task`, `--resume-session`, and `--resume-task`; `--auto` requires an initialized task store and otherwise should point users to `sponte task-plan`.
- App state for `session-resume` is keyed by resolved workspace root; use the same checkout path and `--workspace` convention as the original `sponte agent` run or resume files may be missing even when the CLI printed a resume hint.
- Task `task_id` is path-derived (`t-` + hex); legacy title-based job folders can be renamed with `sponte task-cleanup --migrate-task-ids` when the task file still exists at `rel_task`. `cleanup_pending` defers pruning `.sponte/jobs/tasks/<task_id>/` after completion; `task-cleanup` retries that prune when the task file is gone.
- Selectable tasks are `*.md` files anywhere under `.sponte/tasks/` (excluding `_tmp/` and `artifacts/` subtrees). `.sponte/locks/tasks.lock` lists claimed absolute paths (portability caveats in `docs/concepts/task-lock-caveats.md`). `.sponte/locks/merge.lock` serializes merge; backoff is configured with `merge_backoff_exponential` in `.sponte/settings.json`.
