# Contributing

Sponte is experimental and still shaped around a personal development workflow. Contributions are welcome, but expect the defaults to be opinionated and local-first.

## Local setup

```bash
uv sync --extra dev
uv run pytest
```

For day-to-day changes, run focused tests first, then the full suite before opening a PR:

```bash
uv run pytest tests/test_active_sessions.py
uv run pytest
```

## Scope

- Keep changes small and easy to review.
- Prefer existing patterns over new abstractions.
- Update docs when behavior, defaults, commands, or safety expectations change.
- Treat `.sponte/` runtime data as workspace-owned local state unless the docs explicitly say otherwise.

## Safety

Do not test Sponte against production environments, production credentials, or repositories where fully permissive command execution would be unsafe. Use development checkouts and review diffs before merging.
