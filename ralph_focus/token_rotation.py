"""Token warning / rotation helpers."""

from __future__ import annotations

from dataclasses import dataclass


def derive_warn_threshold(rotate_threshold: int) -> int:
    if rotate_threshold <= 0:
        return 0
    return max(1, int(rotate_threshold * 0.875))


@dataclass(frozen=True)
class TokenRotationPolicy:
    rotate_threshold: int
    warn_threshold: int = 0

    def __post_init__(self) -> None:
        if self.warn_threshold <= 0:
            object.__setattr__(self, "warn_threshold", derive_warn_threshold(self.rotate_threshold))

    def classify(self, total_tokens: int) -> str:
        if self.rotate_threshold > 0 and total_tokens >= self.rotate_threshold:
            return "rotate"
        if self.warn_threshold > 0 and total_tokens >= self.warn_threshold:
            return "warn"
        return "ok"


def rotation_policy_from_overrides(
    *,
    rotate_threshold: int | None,
    warn_threshold: int | None,
    default_rotate_threshold: int,
    default_warn_threshold: int,
) -> TokenRotationPolicy:
    rotate = default_rotate_threshold if rotate_threshold is None else int(rotate_threshold)
    warn = default_warn_threshold if warn_threshold is None else int(warn_threshold)
    return TokenRotationPolicy(rotate_threshold=rotate, warn_threshold=warn)
