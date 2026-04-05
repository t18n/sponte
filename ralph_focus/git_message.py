"""Git commit message rules for agents and orchestrator helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

GIT_MESSAGE_RULES_MARKDOWN = """
## Commit message rules (Ralph / repo)

- **Subject:** first line **50 characters or fewer**.
- **Body:** omit if the subject is enough; else blank line after subject, then short bullets for
  only the most important changes; prose body lines wrap at **72 characters**.
- **No AI attributions:** no trailers such as `Made-with: Cursor` or similar.
- Prefer **Conventional Commits** (`feat:`, `fix:`, `chore:`) per project commitlint.
""".strip()

_AI_TRAILER = re.compile(
    r"(?i)(made-with|generated-with|co-authored-by:\s*cursor|🤖)",
)


@dataclass
class MessageLint:
    warnings: list[str]


def lint_commit_message(msg: str) -> MessageLint:
    warnings: list[str] = []
    lines = msg.strip().splitlines()
    if not lines:
        return MessageLint(["empty message"])
    subj = lines[0]
    if len(subj) > 50:
        warnings.append(f"subject length {len(subj)} > 50")
    if _AI_TRAILER.search(msg):
        warnings.append("possible AI attribution trailer")
    body = lines[1:]
    if body:
        if body[0].strip():
            warnings.append("missing blank line after subject before body")
        for line in body[1:]:
            if len(line) > 72 and line.strip():
                warnings.append(f"body line longer than 72 chars: {line[:40]}…")
    return MessageLint(warnings)


def truncate_subject(label: str, prefix: str = "ralph(auto-focus): ", max_total: int = 50) -> str:
    """Fit orchestrator auto-commit subject under max_total characters."""
    room = max_total - len(prefix)
    if room < 8:
        return prefix[:max_total]
    if len(label) <= room:
        return f"{prefix}{label}"
    return f"{prefix}{label[: room - 1]}…"
