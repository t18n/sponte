# Configuration reference

## File

Workspace defaults live in **`.sponte/settings.json`**. CLI flags override this file for a single run.

## Example

```json
{
  "trunk_branch": "main",
  "worktree_root": ".sponte/worktrees",
  "harness": "cursor",
  "plan_model": "auto",
  "execute_model": "auto",
  "prompts": {
    "implement": ".sponte/prompts/implement.md",
    "agent_pick_task": ".sponte/prompts/agent_pick_task.md"
  },
  "guardrails": {
    "path": ".sponte/guardrails.md"
  },
  "policy": {
    "max_phase_rounds": 20,
    "verification_required": true,
    "merge_required": true
  },
  "commands": {
    "install": "pnpm install",
    "dev": "pnpm run dev",
    "check": "pnpm run check",
    "build": "pnpm run build",
    "test": "pnpm run test",
    "verify": [
      "pnpm run check",
      "pnpm run build",
      "pnpm run test"
    ]
  }
}
```

## Fields

| Key | Meaning |
| --- | --- |
| `trunk_branch` | Default branch for merges and base resolution |
| `worktree_root` | Where Sponte creates task worktrees (relative to repo root unless absolute) |
| `harness` | Built-in id or custom harness configuration from `init` |
| `plan_model` / `execute_model` | Model strings interpreted by the harness |
| `prompts` | Map of built-in prompt name → repo-relative markdown path (resolved at runtime; unknown keys are ignored). Active task-cycle prompt names include `plan`, `implement`, `improve`, `wrap_commit`, `verify`, and `agent_pick_task`. Notable: `agent_pick_task` — template for `sponte agent --auto` markdown-task selection (plan model); placeholders include `__BACKLOG_CANDIDATES__`, `__CLAIMED_TASKS__`, `__NEXT_TASK_FILE__`, `__TASKS_ROOT__`, and task-phase prompts also receive `__TASK_STATUS_FILE__`. |
| `guardrails.path` | Workspace guardrails markdown |
| `policy.max_phase_rounds` | Phase budget before `review-required` |
| `policy.verification_required` | When `false`, VERIFY phase is skipped |
| `policy.merge_required` | When `false`, trunk merge and **primary merge prechecks** are skipped after wrap/verify; you merge manually. Task worktree must still be clean for removal. |
| `commands.install` | Optional: install or sync dependencies for this workspace |
| `commands.dev` | Optional: local run command (e.g. dev server) |
| `commands.check` | Optional: fast validation (lint, typecheck, or a composite script) |
| `commands.build` | Optional: build / compile step |
| `commands.test` | Optional: default automated test command; used as the default verification command when planning new tasks |
| `commands.verify` | Optional: ordered list of shell commands injected into verify-related prompts; when non-empty, overrides `RALPH_VERIFY_COMMANDS` for this workspace |

## Token saver

Workspace `commands` reduce wasted agent turns and output volume:

- `sponte init` pre-fills sensible defaults from manifests (`package.json`, `Cargo.toml`, `go.mod`, Python/pytest hints) so agents see the same commands your team already uses.
- A narrow `check` (or a short `verify` list) often validates a change more cheaply than always running a full build plus full test suite.
- Tune `commands.verify` to match what you actually want before merge; omit heavy steps if your workflow does not need them every cycle.

## Auto-detection rules

- Detection runs at the **repository root** only.
- If **more than one** of these markers is present, Sponte **does not** guess: `Cargo.toml`, `go.mod`, `package.json`, `pyproject.toml` / `requirements.txt`. Set `commands` yourself in that case.
- With exactly one stack, detection follows this order: Rust, then Go, then Node, then Python.
- Re-running `sponte init` on an already-initialized workspace **merges** newly detectable commands into empty fields only; it does not replace values you edited.

## Init validation

`sponte init` probes the selected harness (e.g. `hello`). Invalid harness/model pairs return you to the selection step; only validated values are written.

## Precedence example

`sponte agent --execute-model opus` uses **opus** for that run even if `settings.json` says `auto`.

Verify prompts use workspace `commands.verify` when set; otherwise they use `RALPH_VERIFY_COMMANDS` (documented in the repository README).
