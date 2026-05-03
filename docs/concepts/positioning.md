# Positioning: what Sponte is

Sponte is a **local orchestration layer** for a git workspace: markdown tasks, worktrees, and calls to **official harness CLIs** (Cursor, Claude, Codex, Droid, custom headless wrappers) with prompts and policy.

## What Sponte is not

- Not an IDE, editor, or diff/review UI replacement.
- Not a custom agent framework: it **wraps** upstream CLIs so labs can ship harness changes and subscription compatibility without Sponte re-implementing them.
- Not a sandbox or security boundary: harnesses run with the permissions you give them.

## How to work

Use your normal **IDE**, **git**, and **diff** tools to inspect `.sponte/jobs/`, worktrees, and task files. Sponte coordinates **which** task runs **where** and **when** phases advance; it does not replace careful human review of diffs and provider output.

## Provider reality

Sponte drives native/official harness CLIs and is not intended to bypass provider systems. External services can still impose billing, rate limits, authentication, and policy enforcement.

The stronger local warning is permissions: Sponte is best suited to development workspaces and fully permissive command execution. Do not point it at production environments or credentials. See [provider-safety.md](../guides/provider-safety.md).
