# Sponte Agent Notes

- Use `sponte` for the public CLI/package name. Internal Python modules still live under `ralph_focus/`.
- Prefer `uv run pytest` for verification. Run focused tests while iterating, then the full suite before claiming completion.
- Workspace-aware commands should usually be run with `--workspace /abs/path/to/workspace`.
- In a target workspace, files under `.sponte/` are workspace-owned. Runtime state such as locks, logs, resume files, and handoffs lives outside the repo in Sponte app state.
- If the target workspace has its own instructions, including `AGENTS.md`, `CLAUDE.md`, or `.sponte/guardrails.md`, follow that workspace guidance instead. Treat this file as repo-level guidance for developing Sponte itself.
