import subprocess
import zipfile
from pathlib import Path


def test_built_wheel_includes_prompt_templates(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel = next(dist_dir.glob("sponte-*.whl"))
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())

    assert "prompts/plan.md" in names
    assert "prompts/implement.md" in names
    assert "prompts/verify.md" in names
