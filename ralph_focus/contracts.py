"""Stable boundary contracts for future standalone extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from ralph_focus.failure_detection import FailureClassification, ProgressSnapshot, classify_agent_failure
from ralph_focus.git_ops import worktree_registered
from ralph_focus.paths import (
    auto_focus_logs_dir,
    next_task_file,
    ralph_data_dir,
    resume_file,
    rotation_handoff_file,
)
from ralph_focus.strategies import AgentStrategy, get_strategy
from ralph_focus.tasks import normalize_task_path, priorities_file, priority_task_paths_pending, task_has_pending, task_snapshot

_STREAM_JSON_STRATEGY_IDS = frozenset({"cursor", "droid"})
_KNOWN_NON_STREAM_JSON_STRATEGY_IDS = frozenset({"claude", "codex", "amp", "oz", "warp", "custom"})


@dataclass(frozen=True)
class AvailabilityReport:
    available: bool
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class HarnessCapabilities:
    supports_stream_json: bool = True
    supports_tee_output: bool = True
    supports_metrics_output: bool = True


@dataclass(frozen=True)
class RunRequest:
    cwd: Path
    model: str
    prompt: str
    log_file: Path
    use_stream_json: bool = False
    tee_output: bool = False
    metrics_out: Path | None = None


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class FailureContext:
    summary: str
    detail: str
    no_progress_streak: int
    before: ProgressSnapshot | None = None
    after: ProgressSnapshot | None = None


@dataclass(frozen=True)
class TaskInfo:
    path: Path
    label: str
    pending: int
    done: int


@runtime_checkable
class Harness(Protocol):
    id: str
    display_name: str
    capabilities: HarnessCapabilities

    def availability(self) -> AvailabilityReport:
        ...

    def prepare(self, request: RunRequest) -> RunRequest:
        ...

    def run(self, request: RunRequest) -> RunResult:
        ...

    def classify_failure(self, context: FailureContext) -> FailureClassification:
        ...


@runtime_checkable
class TaskStore(Protocol):
    def resolve_task(self, repo: Path, task_arg: str) -> Path:
        ...

    def priority_tasks(self, repo: Path) -> list[Path]:
        ...

    def task_snapshot(self, task_path: Path) -> TaskInfo:
        ...

    def has_pending(self, task_path: Path) -> bool:
        ...


@runtime_checkable
class ProjectWorkspace(Protocol):
    root: Path

    def default_branch(self) -> str:
        ...

    def is_worktree_registered(self, worktree_path: Path) -> bool:
        ...


@runtime_checkable
class RunStateStore(Protocol):
    root: Path

    def state_root(self) -> Path:
        ...

    def logs_dir(self, *, runner_id: str = "default") -> Path:
        ...

    def resume_file(self, *, runner_id: str = "default") -> Path:
        ...

    def rotation_handoff_file(self, *, runner_id: str = "default") -> Path:
        ...

    def next_task_file(self) -> Path:
        ...


@dataclass
class StrategyHarnessAdapter:
    """Expose an existing AgentStrategy through the new Harness contract."""

    strategy: AgentStrategy
    _display_name: str | None = None
    capabilities: HarnessCapabilities = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", harness_capabilities_for_strategy(self.strategy.id))

    @property
    def id(self) -> str:
        return self.strategy.id

    @property
    def display_name(self) -> str:
        if self._display_name:
            return self._display_name
        return self.id.replace("-", " ").replace("_", " ").title()

    def availability(self) -> AvailabilityReport:
        problems = tuple(self.strategy.check_available())
        return AvailabilityReport(available=not problems, problems=problems)

    def prepare(self, request: RunRequest) -> RunRequest:
        return request

    def run(self, request: RunRequest) -> RunResult:
        exit_code, usage = self.strategy.run(
            request.cwd,
            request.model,
            request.prompt,
            request.log_file,
            use_stream_json=request.use_stream_json,
            tee=request.tee_output,
            metrics_out=request.metrics_out,
        )
        return RunResult(exit_code=exit_code, usage=usage)

    def classify_failure(self, context: FailureContext) -> FailureClassification:
        return classify_agent_failure(
            context.summary,
            context.detail,
            no_progress_streak=context.no_progress_streak,
            before=context.before,
            after=context.after,
        )


def get_harness(name: str) -> Harness:
    return StrategyHarnessAdapter(get_strategy(name))


def harness_capabilities_for_strategy(strategy_id: str) -> HarnessCapabilities:
    if strategy_id in _STREAM_JSON_STRATEGY_IDS:
        supports_stream_json = True
    elif strategy_id in _KNOWN_NON_STREAM_JSON_STRATEGY_IDS:
        supports_stream_json = False
    else:
        supports_stream_json = False
    return HarnessCapabilities(
        supports_stream_json=supports_stream_json,
        supports_tee_output=True,
        supports_metrics_output=supports_stream_json,
    )


@dataclass(frozen=True)
class FileTaskStore:
    """Thin contract adapter around existing markdown task helpers."""

    priorities_filename: str = "priorities.md"

    def resolve_task(self, repo: Path, task_arg: str) -> Path:
        return normalize_task_path(repo, task_arg)

    def priority_tasks(self, repo: Path) -> list[Path]:
        return priority_task_paths_pending(priorities_file(repo, self.priorities_filename), repo)

    def task_snapshot(self, task_path: Path) -> TaskInfo:
        snap = task_snapshot(task_path)
        return TaskInfo(path=task_path, label=snap.label, pending=snap.pending, done=snap.done)

    def has_pending(self, task_path: Path) -> bool:
        return task_has_pending(task_path)


@dataclass(frozen=True)
class RepoProjectWorkspace:
    """Git/worktree contract adapter for a single repository root."""

    root: Path

    def default_branch(self) -> str:
        from ralph_focus.workspace_resolve import resolve_trunk_branch_ref

        return resolve_trunk_branch_ref(self.root, cli_override=None)

    def is_worktree_registered(self, worktree_path: Path) -> bool:
        return worktree_registered(self.root, worktree_path)


@dataclass(frozen=True)
class FileSystemRunStateStore:
    """Runtime-state path contract adapter for the current repo layout."""

    root: Path

    def state_root(self) -> Path:
        return ralph_data_dir(self.root)

    def logs_dir(self, *, runner_id: str = "default") -> Path:
        return auto_focus_logs_dir(self.root, runner_id=runner_id)

    def resume_file(self, *, runner_id: str = "default") -> Path:
        return resume_file(self.root, runner_id=runner_id)

    def rotation_handoff_file(self, *, runner_id: str = "default") -> Path:
        return rotation_handoff_file(self.root, runner_id=runner_id)

    def next_task_file(self) -> Path:
        return next_task_file(self.root)


__all__ = [
    "AvailabilityReport",
    "FailureContext",
    "FileSystemRunStateStore",
    "FileTaskStore",
    "Harness",
    "HarnessCapabilities",
    "harness_capabilities_for_strategy",
    "ProjectWorkspace",
    "RepoProjectWorkspace",
    "RunRequest",
    "RunResult",
    "RunStateStore",
    "StrategyHarnessAdapter",
    "TaskInfo",
    "TaskStore",
    "get_harness",
]
