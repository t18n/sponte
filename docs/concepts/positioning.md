# Positioning: what Sponte is

Sponte is a **local orchestration layer** for a git workspace: markdown tasks, worktrees, and calls to **official harness CLIs** (Cursor, Claude, Codex, Droid, custom headless wrappers) with prompts and policy.

## What Sponte is not

- Not an IDE, editor, or diff/review UI replacement.
- Not a custom agent framework: it **wraps** upstream CLIs so labs can ship harness changes and subscription compatibility without Sponte re-implementing them.

## How to work

Use your normal **IDE**, **git**, and **diff** tools to inspect `.sponte/jobs/`, worktrees, and task files. Sponte coordinates **which** task runs **where** and **when** phases advance; it does not replace careful human review of diffs and provider output.

## Provider reality

External services can still impose billing, rate limits, or policy enforcement. Sponte cannot guarantee protection from provider-side surprises. Prefer conservative usage; see [provider-safety.md](../guides/provider-safety.md).
