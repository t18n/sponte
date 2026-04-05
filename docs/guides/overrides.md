# Prompts, guardrails, and models

## Precedence

1. **CLI flags** (e.g. harness, `--plan-model`, `--execute-model`)
2. **`.sponte/settings.json`**
3. Built-in defaults

## Prompt and guardrail files

- **`settings.json` → `prompts`**: map built-in prompt ids to **repo-relative** files under `.sponte/prompts/`. Override is **full-file replacement**: if the file exists, Sponte uses it instead of the bundled template; there is no merge/patch layer.
- **`settings.json` → `guardrails`**: path to markdown (default `.sponte/guardrails.md`).

## Models

`plan_model` and `execute_model` are validated during `init` against the chosen harness. Invalid combinations send you back to selection; only validated values are persisted.
