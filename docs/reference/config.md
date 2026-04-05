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
    "followup_tickets": ".sponte/prompts/followup_tickets.md"
  },
  "guardrails": {
    "path": ".sponte/guardrails.md"
  },
  "policy": {
    "max_phase_rounds": 20,
    "verification_required": true,
    "merge_required": true
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
| `prompts` | Map of built-in prompt name → repo-relative markdown path |
| `guardrails.path` | Workspace guardrails markdown |
| `policy.max_phase_rounds` | Phase budget before `review-required` |
| `policy.verification_required` | When `false`, VERIFY phase is skipped |
| `policy.merge_required` | When `false`, trunk merge and **primary merge prechecks** are skipped after wrap; you merge manually. Task worktree must still be clean for removal. |

## Init validation

`sponte init` probes the selected harness (e.g. `hello`). Invalid harness/model pairs return you to the selection step; only validated values are written.

## Precedence example

`sponte agent --execute-model opus` uses **opus** for that run even if `settings.json` says `auto`.
