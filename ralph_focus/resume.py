"""Resume state under app state ``runners/<id>/agent/resume.state`` (shell export format).

Legacy installs may still have ``runners/<id>/auto-focus/resume.state``; :func:`load_resume`
reads that path when the new location is absent.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from config.defaults import LEGACY_RALPH_DATA_DIR, RESUME_SCHEMA_VERSION
from ralph_focus.paths import (
    auto_focus_data_dir,
    plan_file_for_task,
    ralph_data_dir,
    resume_file,
    resume_file_legacy,
)
from ralph_focus.tasks import normalize_task_rel


class ResumeLoadFailureReason(str, Enum):
    """Why :func:`load_resume` would return ``None`` for this workspace + runner id."""

    missing_file = "missing_file"
    invalid_schema = "invalid_schema"
    invalid_version = "invalid_version"
    primary_mismatch = "primary_mismatch"
    empty_required_fields = "empty_required_fields"
    invalid_numeric_fields = "invalid_numeric_fields"


@dataclass
class ResumeState:
    schema_version: int = RESUME_SCHEMA_VERSION
    primary: str = ""
    phase: str = "PLAN"
    logf: str = ""
    wt_path: str = ""
    branch: str = ""
    main_ref: str = ""
    rel_task: str = ""
    plan_rel: str = ""
    implement_next: int = 1
    improve_i: int = 1
    improve_j: int = 0
    consistency_j: int = 0
    conflict_next: int = 1
    cycles_done: int = 0
    max_cycles: str = ""
    task_arg: str = ""
    agent_kind: str = "cursor"
    plan_model: str = ""
    agent_model: str = ""
    allow_agent_pick: str = "false"
    session_deadline_epoch: str = ""
    total_tokens: int = 0
    no_progress_loops: int = 0
    token_warning_emitted: str = "false"
    # Generation id for CLI --resume-session / locks; may differ from runners/<segment>/ when segment is hashed.
    resume_runner_id: str = ""
    task_id: str = ""

    def to_exports(self) -> dict[str, str]:
        return {
            "R_RESUME_SCHEMA_VERSION": str(self.schema_version),
            "R_RESUME_PRIMARY": self.primary,
            "R_RESUME_PHASE": self.phase,
            "R_RESUME_LOGF": self.logf,
            "R_RESUME_WT_PATH": self.wt_path,
            "R_RESUME_BRANCH": self.branch,
            "R_RESUME_MAIN_REF": self.main_ref,
            "R_RESUME_REL_TASK": self.rel_task,
            "R_RESUME_PLAN_REL": self.plan_rel,
            "R_RESUME_IMPLEMENT_NEXT": str(self.implement_next),
            "R_RESUME_IMPROVE_I": str(self.improve_i),
            "R_RESUME_IMPROVE_J": str(self.improve_j),
            "R_RESUME_CONSISTENCY_J": str(self.consistency_j),
            "R_RESUME_CONFLICT_NEXT": str(self.conflict_next),
            "R_RESUME_CYCLES_DONE": str(self.cycles_done),
            "R_RESUME_MAX_CYCLES": self.max_cycles,
            "R_RESUME_TASK_ARG": self.task_arg,
            "R_RESUME_AGENT_KIND": self.agent_kind,
            "R_RESUME_PLAN_MODEL": self.plan_model,
            "R_RESUME_AGENT_MODEL": self.agent_model,
            "R_RESUME_ALLOW_AGENT_PICK": self.allow_agent_pick,
            "R_RESUME_SESSION_DEADLINE_EPOCH": self.session_deadline_epoch,
            "R_RESUME_TOTAL_TOKENS": str(self.total_tokens),
            "R_RESUME_NO_PROGRESS_LOOPS": str(self.no_progress_loops),
            "R_RESUME_TOKEN_WARNING_EMITTED": self.token_warning_emitted,
            "R_RESUME_RUNNER_ID": self.resume_runner_id,
            "R_RESUME_TASK_ID": self.task_id,
        }


def write_resume(
    primary: Path,
    state: ResumeState,
    *,
    runner_id: str = "default",
) -> None:
    rid = runner_id.strip()
    to_write = state if (state.resume_runner_id or "").strip() or not rid else replace(state, resume_runner_id=rid)
    path = resume_file(primary, runner_id=runner_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# ralph resume (generated; do not hand-edit)"]
    for k, v in to_write.to_exports().items():
        lines.append(f"export {k}={shlex.quote(v)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clear_resume(
    primary: Path,
    *,
    runner_id: str = "default",
) -> None:
    resume_file(primary, runner_id=runner_id).unlink(missing_ok=True)
    resume_file_legacy(primary, runner_id=runner_id).unlink(missing_ok=True)


def update_resume_runtime_state(
    primary: Path,
    *,
    runner_id: str = "default",
    total_tokens: int | None = None,
    token_warning_emitted: bool | None = None,
) -> None:
    state = load_resume(primary, runner_id=runner_id)
    if state is None:
        return
    updated = state
    if total_tokens is not None:
        updated = replace(updated, total_tokens=int(total_tokens))
    if token_warning_emitted is not None:
        updated = replace(
            updated,
            token_warning_emitted="true" if token_warning_emitted else "false",
        )
    write_resume(primary, updated, runner_id=runner_id)


def _parse_export_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line.startswith("export "):
        return None
    rest = line[7:].strip()
    if "=" not in rest:
        return None
    key, _, val = rest.partition("=")
    key = key.strip()
    try:
        parsed = shlex.split(val, posix=True)
    except ValueError:
        return None
    if len(parsed) != 1:
        return None
    return key, parsed[0]


def _parse_int(raw: dict[str, str], key: str, default: int) -> int | None:
    value = raw.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return None


def load_resume(
    primary: Path,
    *,
    runner_id: str = "default",
) -> ResumeState | None:
    st, _reason = load_resume_detailed(primary, runner_id=runner_id)
    return st


def load_resume_detailed(
    primary: Path,
    *,
    runner_id: str = "default",
) -> tuple[ResumeState | None, ResumeLoadFailureReason | None]:
    """
    Like :func:`load_resume` but returns a failure reason when state is unusable.

    ``(state, None)`` on success; ``(None, reason)`` on failure; ``(None, None)`` should not occur.
    """
    path = resume_file(primary, runner_id=runner_id)
    if not path.is_file():
        leg = resume_file_legacy(primary, runner_id=runner_id)
        if not leg.is_file():
            return None, ResumeLoadFailureReason.missing_file
        path = leg
    raw: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        p = _parse_export_line(line)
        if p:
            raw[p[0]] = p[1]
    ver = _parse_int(raw, "R_RESUME_SCHEMA_VERSION", 0)
    if ver is None:
        return None, ResumeLoadFailureReason.invalid_schema
    if ver not in (1, 2, 3):
        return None, ResumeLoadFailureReason.invalid_version
    if raw.get("R_RESUME_PRIMARY", "") != str(primary.resolve()):
        return None, ResumeLoadFailureReason.primary_mismatch
    if not raw.get("R_RESUME_WT_PATH") or not raw.get("R_RESUME_REL_TASK") or not raw.get("R_RESUME_LOGF"):
        return None, ResumeLoadFailureReason.empty_required_fields
    rel_task = normalize_task_rel(raw.get("R_RESUME_REL_TASK", ""))
    plan_rel = raw.get("R_RESUME_PLAN_REL", "")
    if plan_rel.startswith(".ralph/data/"):
        plan_rel = f"{LEGACY_RALPH_DATA_DIR}/{plan_rel.removeprefix('.ralph/data/')}"
    legacy_plans_prefix = f"{LEGACY_RALPH_DATA_DIR}/plans/"
    if plan_rel.startswith(legacy_plans_prefix):
        stem = Path(plan_rel.removeprefix(legacy_plans_prefix)).stem
        plan_rel = plan_file_for_task(primary, stem).resolve().as_posix()
    implement_next = _parse_int(raw, "R_RESUME_IMPLEMENT_NEXT", 1)
    improve_i = _parse_int(raw, "R_RESUME_IMPROVE_I", 1)
    improve_j = _parse_int(raw, "R_RESUME_IMPROVE_J", 0)
    consistency_j = _parse_int(raw, "R_RESUME_CONSISTENCY_J", 0)
    conflict_next = _parse_int(raw, "R_RESUME_CONFLICT_NEXT", 1)
    cycles_done = _parse_int(raw, "R_RESUME_CYCLES_DONE", 0)
    total_tokens = _parse_int(raw, "R_RESUME_TOTAL_TOKENS", 0)
    no_progress_loops = _parse_int(raw, "R_RESUME_NO_PROGRESS_LOOPS", 0)
    numeric_values = (
        implement_next,
        improve_i,
        improve_j,
        consistency_j,
        conflict_next,
        cycles_done,
        total_tokens,
        no_progress_loops,
    )
    if any(value is None for value in numeric_values):
        return None, ResumeLoadFailureReason.invalid_numeric_fields
    return (
        ResumeState(
            schema_version=ver,
            primary=raw.get("R_RESUME_PRIMARY", ""),
            phase=raw.get("R_RESUME_PHASE", "PLAN"),
            logf=raw.get("R_RESUME_LOGF", ""),
            wt_path=raw.get("R_RESUME_WT_PATH", ""),
            branch=raw.get("R_RESUME_BRANCH", ""),
            main_ref=raw.get("R_RESUME_MAIN_REF", ""),
            rel_task=rel_task,
            plan_rel=plan_rel,
            implement_next=implement_next,
            improve_i=improve_i,
            improve_j=improve_j,
            consistency_j=consistency_j,
            conflict_next=conflict_next,
            cycles_done=cycles_done,
            max_cycles=raw.get("R_RESUME_MAX_CYCLES", ""),
            task_arg=raw.get("R_RESUME_TASK_ARG", ""),
            agent_kind=raw.get("R_RESUME_AGENT_KIND", "cursor"),
            plan_model=raw.get("R_RESUME_PLAN_MODEL", ""),
            agent_model=raw.get("R_RESUME_AGENT_MODEL", ""),
            allow_agent_pick=raw.get("R_RESUME_ALLOW_AGENT_PICK", "false"),
            session_deadline_epoch=raw.get("R_RESUME_SESSION_DEADLINE_EPOCH", ""),
            total_tokens=total_tokens,
            no_progress_loops=no_progress_loops,
            token_warning_emitted=raw.get("R_RESUME_TOKEN_WARNING_EMITTED", "false"),
            resume_runner_id=raw.get("R_RESUME_RUNNER_ID", ""),
            task_id=raw.get("R_RESUME_TASK_ID", ""),
        ),
        None,
    )


def list_recoverable_resumes(primary: Path) -> list[tuple[str, ResumeState]]:
    """Return `(session_runner_id, state)` for each valid `resume.state` under app state runners."""
    runners_root = ralph_data_dir(primary) / "runners"
    if not runners_root.is_dir():
        return []
    out: list[tuple[str, ResumeState]] = []
    for child in sorted(runners_root.iterdir()):
        if not child.is_dir():
            continue
        seg = child.name
        st = load_resume(primary, runner_id=seg)
        if st is None:
            continue
        session_id = (st.resume_runner_id or seg).strip() or seg
        out.append((session_id, st))
    return out


def resolve_runner_for_worktree(primary: Path, worktree: Path) -> tuple[str, ResumeState] | None:
    """Map a worktree path to the session runner id and resume state; `None` if unknown or ambiguous."""
    try:
        want = worktree.expanduser().resolve()
    except OSError:
        return None
    matches: list[tuple[str, ResumeState]] = []
    for rid, st in list_recoverable_resumes(primary):
        try:
            if Path(st.wt_path).expanduser().resolve() == want:
                matches.append((rid, st))
        except OSError:
            continue
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_runner_for_task_id(primary: Path, task_id: str) -> tuple[str, ResumeState] | None:
    """Map a persisted ``task_id`` to the session runner id and resume state; ``None`` if unknown or ambiguous."""
    want = task_id.strip()
    if not want:
        return None
    matches: list[tuple[str, ResumeState]] = []
    for rid, st in list_recoverable_resumes(primary):
        tid = (st.task_id or "").strip()
        if tid == want:
            matches.append((rid, st))
    if len(matches) == 1:
        return matches[0]
    return None


def resume_path(
    primary: Path,
    *,
    runner_id: str = "default",
) -> Path:
    return resume_file(primary, runner_id=runner_id)


def runner_data_root(primary: Path, runner_id: str) -> Path:
    """Parent of logs/resume for this runner (for docs / introspection)."""
    return auto_focus_data_dir(primary, runner_id)
