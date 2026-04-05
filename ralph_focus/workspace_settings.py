"""Per-workspace settings stored under ``workspace/.sponte/`` (not app state)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.defaults import DEFAULT_AGENT, DEFAULT_EXECUTE_MODEL, DEFAULT_PLAN_MODEL, SPONTE_DIR

SETTINGS_FILENAME = "settings.json"
DEFAULT_TRUNK_BRANCH = "sponte"
DEFAULT_WORKTREE_ROOT = ".sponte/worktrees"
DEFAULT_GUARDRAILS_REL = ".sponte/guardrails.md"


@dataclass
class CustomHarnessConfig:
    """Thin headless CLI definition when ``harness`` is ``custom``."""

    executable: str = ""
    args: tuple[str, ...] = ()
    probe: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, raw: object) -> CustomHarnessConfig | None:
        if not isinstance(raw, dict):
            return None
        exe = raw.get("executable")
        if not isinstance(exe, str) or not exe.strip():
            return None

        def as_str_tuple(key: str) -> tuple[str, ...]:
            v = raw.get(key)
            if not isinstance(v, list):
                return ()
            return tuple(str(x).strip() for x in v if str(x).strip())

        return cls(executable=exe.strip(), args=as_str_tuple("args"), probe=as_str_tuple("probe"))


@dataclass
class WorkspacePolicy:
    max_phase_rounds: int = 20
    verification_required: bool = True
    merge_required: bool = True

    @classmethod
    def from_json(cls, raw: object) -> WorkspacePolicy:
        if not isinstance(raw, dict):
            return cls()
        rounds = raw.get("max_phase_rounds", 20)
        try:
            mpr = int(rounds) if rounds is not None else 20
        except (TypeError, ValueError):
            mpr = 20
        vr = raw.get("verification_required", True)
        mr = raw.get("merge_required", True)
        return cls(
            max_phase_rounds=max(1, mpr),
            verification_required=bool(vr) if isinstance(vr, bool) else str(vr).lower() in ("1", "true", "yes"),
            merge_required=bool(mr) if isinstance(mr, bool) else str(mr).lower() in ("1", "true", "yes"),
        )


@dataclass
class WorkspaceCommandSettings:
    """Per-workspace lifecycle commands (see docs for semantics and token-saving tips)."""

    install: str = ""
    dev: str = ""
    check: str = ""
    build: str = ""
    test: str = ""
    verify: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, raw: object) -> WorkspaceCommandSettings:
        if not isinstance(raw, dict):
            return cls()

        def opt_str(key: str) -> str:
            v = raw.get(key)
            return v.strip() if isinstance(v, str) and v.strip() else ""

        verify_raw = raw.get("verify")
        verify_t: tuple[str, ...] = ()
        if isinstance(verify_raw, list):
            verify_t = tuple(str(x).strip() for x in verify_raw if str(x).strip())

        return cls(
            install=opt_str("install"),
            dev=opt_str("dev"),
            check=opt_str("check"),
            build=opt_str("build"),
            test=opt_str("test"),
            verify=verify_t,
        )

    def to_json_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.install:
            out["install"] = self.install
        if self.dev:
            out["dev"] = self.dev
        if self.check:
            out["check"] = self.check
        if self.build:
            out["build"] = self.build
        if self.test:
            out["test"] = self.test
        if self.verify:
            out["verify"] = list(self.verify)
        return out


def merge_command_settings(
    current: WorkspaceCommandSettings,
    detected: WorkspaceCommandSettings,
) -> WorkspaceCommandSettings:
    """Fill only empty fields from *detected*; user-configured values win."""
    return WorkspaceCommandSettings(
        install=current.install or detected.install,
        dev=current.dev or detected.dev,
        check=current.check or detected.check,
        build=current.build or detected.build,
        test=current.test or detected.test,
        verify=current.verify if current.verify else detected.verify,
    )


@dataclass
class WorkspaceSettings:
    trunk_branch: str = DEFAULT_TRUNK_BRANCH
    worktree_root: str = DEFAULT_WORKTREE_ROOT
    harness: str = ""
    plan_model: str = ""
    execute_model: str = ""
    prompts: dict[str, str] = field(default_factory=dict)
    guardrails_path: str = ""
    policy: WorkspacePolicy = field(default_factory=WorkspacePolicy)
    custom_harness: CustomHarnessConfig | None = None
    commands: WorkspaceCommandSettings = field(default_factory=WorkspaceCommandSettings)

    def normalized_trunk(self) -> str:
        s = self.trunk_branch.strip()
        return s if s else DEFAULT_TRUNK_BRANCH

    def normalized_worktree_root(self) -> str:
        s = self.worktree_root.strip()
        return s if s else DEFAULT_WORKTREE_ROOT

    def resolved_harness_id(self) -> str:
        h = self.harness.strip().lower()
        if h == "custom":
            return "custom"
        return h if h else DEFAULT_AGENT

    def resolved_plan_model(self) -> str:
        s = self.plan_model.strip()
        return s if s else DEFAULT_PLAN_MODEL

    def resolved_execute_model(self) -> str:
        s = self.execute_model.strip()
        return s if s else DEFAULT_EXECUTE_MODEL

    def normalized_guardrails_path(self) -> str:
        s = self.guardrails_path.strip()
        return s if s else DEFAULT_GUARDRAILS_REL


def workspace_settings_path(root: Path) -> Path:
    return root / SPONTE_DIR / SETTINGS_FILENAME


def _prompts_from_json(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            out[k.strip()] = v.strip()
    return out


def load_workspace_settings(root: Path) -> WorkspaceSettings:
    path = workspace_settings_path(root)
    if not path.is_file():
        return WorkspaceSettings()
    try:
        raw_any: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return WorkspaceSettings()
    if not isinstance(raw_any, dict):
        return WorkspaceSettings()
    raw = raw_any
    trunk = raw.get("trunk_branch")
    worktree_root = raw.get("worktree_root")
    harness = raw.get("harness")
    plan_model = raw.get("plan_model")
    execute_model = raw.get("execute_model")
    prompts_raw = raw.get("prompts")
    guardrails = raw.get("guardrails")
    policy_raw = raw.get("policy")
    custom_raw = raw.get("custom_harness")
    commands_raw = raw.get("commands")

    guardrails_path = ""
    if isinstance(guardrails, dict):
        gp = guardrails.get("path")
        if isinstance(gp, str) and gp.strip():
            guardrails_path = gp.strip()
    elif isinstance(guardrails, str) and guardrails.strip():
        guardrails_path = guardrails.strip()

    custom = CustomHarnessConfig.from_json(custom_raw) if custom_raw is not None else None

    return WorkspaceSettings(
        trunk_branch=trunk.strip() if isinstance(trunk, str) and trunk.strip() else DEFAULT_TRUNK_BRANCH,
        worktree_root=(
            worktree_root.strip()
            if isinstance(worktree_root, str) and worktree_root.strip()
            else DEFAULT_WORKTREE_ROOT
        ),
        harness=harness.strip() if isinstance(harness, str) else "",
        plan_model=plan_model.strip() if isinstance(plan_model, str) else "",
        execute_model=execute_model.strip() if isinstance(execute_model, str) else "",
        prompts=_prompts_from_json(prompts_raw),
        guardrails_path=guardrails_path,
        policy=WorkspacePolicy.from_json(policy_raw),
        custom_harness=custom,
        commands=(
            WorkspaceCommandSettings.from_json(commands_raw)
            if isinstance(commands_raw, dict)
            else WorkspaceCommandSettings()
        ),
    )


def save_workspace_settings(root: Path, settings: WorkspaceSettings) -> None:
    path = workspace_settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    gh = settings.custom_harness
    custom_payload: dict[str, Any] | None = None
    if gh is not None and gh.executable:
        custom_payload = {
            "executable": gh.executable,
            "args": list(gh.args),
            "probe": list(gh.probe),
        }
    payload: dict[str, Any] = {
        "trunk_branch": settings.normalized_trunk(),
        "worktree_root": settings.normalized_worktree_root(),
        "harness": settings.harness.strip() or DEFAULT_AGENT,
        "plan_model": settings.plan_model.strip() or DEFAULT_PLAN_MODEL,
        "execute_model": settings.execute_model.strip() or DEFAULT_EXECUTE_MODEL,
        "prompts": dict(settings.prompts),
        "guardrails": {"path": settings.normalized_guardrails_path()},
        "policy": {
            "max_phase_rounds": settings.policy.max_phase_rounds,
            "verification_required": settings.policy.verification_required,
            "merge_required": settings.policy.merge_required,
        },
    }
    cmd_payload = settings.commands.to_json_dict()
    if cmd_payload:
        payload["commands"] = cmd_payload
    if custom_payload is not None:
        payload["custom_harness"] = custom_payload
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "DEFAULT_TRUNK_BRANCH",
    "DEFAULT_WORKTREE_ROOT",
    "CustomHarnessConfig",
    "WorkspaceCommandSettings",
    "WorkspacePolicy",
    "WorkspaceSettings",
    "load_workspace_settings",
    "merge_command_settings",
    "save_workspace_settings",
    "workspace_settings_path",
]
