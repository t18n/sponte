# Sponte Guardrails

> Lightweight bootstrap guardrails for the standalone Sponte repo.

## Core Signs

### Sign: Read Before Writing
- **Trigger**: Before modifying any file
- **Instruction**: Read the existing file first

### Sign: Verify After Changes
- **Trigger**: After code or prompt changes
- **Instruction**: Run the smallest relevant verification before claiming success

### Sign: Prefer Installed CLI
- **Trigger**: Running Sponte from this repo
- **Instruction**: Prefer `uv run sponte ...` after `uv sync`

## Notes

- Internal runtime state still lives under `.agents/ralph/` in this bootstrap phase.
- Add new durable lessons here as standalone-specific issues are discovered.
