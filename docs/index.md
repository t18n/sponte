# Sponte documentation

Sponte is a **local orchestration CLI** for git workspaces: markdown tasks, worktrees, and **official harness CLIs** in headless mode. It does not replace your IDE, editor, or diff tools.

## Start here

- [Getting started](guides/getting-started.md)
- [Concepts overview](concepts/overview.md)
- [CLI reference](reference/cli.md)
- [Configuration](reference/config.md)

## Concepts

| Topic | Description |
| --- | --- |
| [Overview](concepts/overview.md) | Tasks, sessions, worktrees, source of truth |
| [Tasks and sessions](concepts/tasks-and-sessions.md) | Lifecycle and `task_id` |
| [Session vs task ownership](concepts/session-task-ownership.md) | Invariants, resume vs reclaim |
| [State model](concepts/state-model.md) | `.sponte` vs app state |
| [Job folders](concepts/job-folders.md) | `.sponte/jobs/` dual index |
| [Task states](concepts/task-states.md) | Backlog → completed, `review-required` |
| [Backpressure / policy](concepts/backpressure.md) | `max_phase_rounds`, verify, merge |
| [Observability](concepts/observability.md) | `status`, `stats`, events |
| [Positioning](concepts/positioning.md) | Orchestration layer, not an IDE |

## Guides

| Topic | Description |
| --- | --- |
| [Migrating from auto-focus](guides/migrating-from-auto-focus.md) | Renamed commands and paths |
| [Custom harnesses](guides/custom-harnesses.md) | Headless custom executables |
| [Overrides](guides/overrides.md) | Prompts, guardrails, precedence |
| [Review required](guides/review-required.md) | After max phase rounds |
| [Provider and local safety](guides/provider-safety.md) | Native CLIs, full permissions, billing, and policy caution |

## Reference

- [CLI](reference/cli.md)
- [Config schema](reference/config.md)
- [Task files & `task_id`](reference/task-files.md)
