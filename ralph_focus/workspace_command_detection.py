"""Best-effort detection of workspace lifecycle commands from repo manifests."""

from __future__ import annotations

import json
from pathlib import Path

from ralph_focus.workspace_settings import WorkspaceCommandSettings

# Fallback when settings and detection yield no test command (matches non-uv Python detection).
DEFAULT_FALLBACK_TEST_COMMAND = "python -m pytest -q"


def _ecosystem_marker_count(root: Path) -> int:
    """Count distinct root-level stacks; >1 means we skip auto-detection."""
    n = 0
    if (root / "Cargo.toml").is_file():
        n += 1
    if (root / "go.mod").is_file():
        n += 1
    if (root / "package.json").is_file():
        n += 1
    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        n += 1
    return n


def _ordered_verify(parts: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return tuple(out)


def _detect_package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "bun.lockb").is_file():
        return "bun"
    if (root / "package-lock.json").is_file():
        return "npm"
    return "npm"


def _script_cmd(pm: str, script: str) -> str:
    if pm == "pnpm":
        return f"pnpm run {script}"
    if pm == "yarn":
        return f"yarn {script}"
    if pm == "bun":
        return f"bun run {script}"
    return f"npm run {script}"


def _install_cmd(pm: str, root: Path) -> str:
    if pm == "pnpm":
        return "pnpm install"
    if pm == "yarn":
        return "yarn install"
    if pm == "bun":
        return "bun install"
    if (root / "package-lock.json").is_file():
        return "npm ci"
    return "npm install"


def _node_check_script(scripts: dict[str, str], pm: str) -> str:
    if "check" in scripts:
        return _script_cmd(pm, "check")
    has_lint = "lint" in scripts
    has_tc = "typecheck" in scripts
    if has_lint and has_tc:
        return f"{_script_cmd(pm, 'lint')} && {_script_cmd(pm, 'typecheck')}"
    if has_lint:
        return _script_cmd(pm, "lint")
    if has_tc:
        return _script_cmd(pm, "typecheck")
    return ""


def _detect_node(root: Path) -> WorkspaceCommandSettings:
    path = root / "package.json"
    if not path.is_file():
        return WorkspaceCommandSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return WorkspaceCommandSettings()
    if not isinstance(data, dict):
        return WorkspaceCommandSettings()
    scripts_raw = data.get("scripts")
    if not isinstance(scripts_raw, dict):
        scripts = {}
    else:
        scripts = {str(k): str(v) for k, v in scripts_raw.items() if isinstance(k, str) and isinstance(v, str)}

    pm = _detect_package_manager(root)
    install = _install_cmd(pm, root)
    dev = _script_cmd(pm, "dev") if "dev" in scripts else ""
    build = _script_cmd(pm, "build") if "build" in scripts else ""
    test = _script_cmd(pm, "test") if "test" in scripts else ""
    check = _node_check_script(scripts, pm)

    verify_parts: list[str] = []
    if check:
        verify_parts.append(check)
    if build:
        verify_parts.append(build)
    if test:
        verify_parts.append(test)
    verify = _ordered_verify(tuple(verify_parts))

    return WorkspaceCommandSettings(
        install=install,
        dev=dev,
        check=check,
        build=build,
        test=test,
        verify=verify,
    )


def _detect_rust(root: Path) -> WorkspaceCommandSettings:
    if not (root / "Cargo.toml").is_file():
        return WorkspaceCommandSettings()
    check = "cargo check"
    build = "cargo build"
    test = "cargo test"
    return WorkspaceCommandSettings(
        check=check,
        build=build,
        test=test,
        verify=_ordered_verify((check, build, test)),
    )


def _detect_go(root: Path) -> WorkspaceCommandSettings:
    if not (root / "go.mod").is_file():
        return WorkspaceCommandSettings()
    build = "go build ./..."
    test = "go test ./..."
    return WorkspaceCommandSettings(
        build=build,
        test=test,
        verify=_ordered_verify((build, test)),
    )


def _python_suggests_pytest(root: Path, pyproject_text: str) -> bool:
    low = pyproject_text.lower()
    if "pytest" in low or "pytest.ini_options" in low:
        return True
    req = root / "requirements.txt"
    if req.is_file():
        if "pytest" in req.read_text(encoding="utf-8", errors="replace").lower():
            return True
    return False


def _detect_python(root: Path) -> WorkspaceCommandSettings:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file() and not (root / "requirements.txt").is_file():
        return WorkspaceCommandSettings()
    py_text = ""
    if pyproject.is_file():
        py_text = pyproject.read_text(encoding="utf-8", errors="replace")
    if not _python_suggests_pytest(root, py_text):
        return WorkspaceCommandSettings()

    has_build = pyproject.is_file() and "[build-system]" in py_text
    install = ""
    test = ""
    if (root / "uv.lock").is_file():
        install = "uv sync"
        test = "uv run pytest -q"
    else:
        test = "python -m pytest -q"
        if (root / "requirements.txt").is_file():
            install = "python -m pip install -r requirements.txt"
        elif pyproject.is_file():
            install = "pip install -e ."

    build = "python -m build" if has_build else ""
    verify_parts: list[str] = []
    if build:
        verify_parts.append(build)
    if test:
        verify_parts.append(test)
    verify = _ordered_verify(tuple(verify_parts)) if verify_parts else ()
    return WorkspaceCommandSettings(install=install, build=build, test=test, verify=verify)


def detect_workspace_commands(root: Path) -> WorkspaceCommandSettings:
    """
    Infer install/dev/check/build/test/verify for *root* using a single primary stack.

    If multiple ecosystem markers exist at the repo root (e.g. ``Cargo.toml`` and
    ``package.json``), returns empty settings so users are not given arbitrary defaults.

    Priority when exactly one marker set applies: Rust, Go, Node, Python.
    """
    r = root.resolve()
    if _ecosystem_marker_count(r) > 1:
        return WorkspaceCommandSettings()
    if (r / "Cargo.toml").is_file():
        return _detect_rust(r)
    if (r / "go.mod").is_file():
        return _detect_go(r)
    if (r / "package.json").is_file():
        return _detect_node(r)
    return _detect_python(r)


def resolved_default_test_command(root: Path) -> str:
    """
    Default ``test_command`` for new tasks: saved ``commands.test``, else fresh detection, else pytest.
    """
    from ralph_focus.workspace_settings import load_workspace_settings

    ws = load_workspace_settings(root)
    if ws.commands.test.strip():
        return ws.commands.test.strip()
    det = detect_workspace_commands(root)
    if det.test.strip():
        return det.test.strip()
    return DEFAULT_FALLBACK_TEST_COMMAND


__all__ = [
    "DEFAULT_FALLBACK_TEST_COMMAND",
    "detect_workspace_commands",
    "resolved_default_test_command",
]
