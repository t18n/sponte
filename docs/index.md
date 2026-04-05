# Sponte documentation

Sponte is a **local orchestration CLI** for software workspaces: it manages markdown tasks, git worktrees, and calls **official agent harness CLIs** (Cursor, Claude, Codex, Droid, …) in headless mode. It does not replace your IDE, editor, or diff tools.

## Start here

- [Concepts overview](concepts/overview.md) — tasks, sessions, worktrees, and where state lives
- [CLI reference](reference/cli.md) — command list and short semantics

## Concepts (selected)

| Topic | File |
| --- | --- |
| Tasks vs sessions | [concepts/overview.md](concepts/overview.md) |
| `.sponte/jobs/` layout | README “Workspace Model” + [reference/cli.md](reference/cli.md) |
| Provider / billing caution | README “Provider usage” |

## Guides (placeholders for expansion)

Future pages can cover custom harnesses, `review-required`, and `task-cleanup` in depth; the CLI help strings and README already describe current behavior.
