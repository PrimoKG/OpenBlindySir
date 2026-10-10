"""Windows Docker builds must not traverse unrelated local folders."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is unavailable")


def ps_quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def run_script(script: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )


def test_checkout_build_excludes_local_artifacts(tmp_path: Path) -> None:
    # Use the checkout itself: developer machines may have unreadable test outputs.
    result = run_script(
        "$ErrorActionPreference = 'Stop'; "
        f". {ps_quote(ROOT / 'tools/docker-context.ps1')}; "
        f"New-DockerBuildContext {ps_quote(ROOT)} {ps_quote(tmp_path)}"
    )
    assert result.returncode == 0, result.stderr
    context = Path(result.stdout.strip())
    assert (context / "Dockerfile").is_file()
    assert (context / "web/package-lock.json").is_file()
    for lock in ("go.mod", "go.sum"):
        assert (context / "deploy/proxy" / lock).read_bytes() == (
            ROOT / "deploy/proxy" / lock
        ).read_bytes()
    for package in ("protocol", "server", "bridge"):
        assert (context / package / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    assert (context / "bridge/README.md").is_file()
    assert any((context / "server/src").rglob("*.py"))
    assert any((context / "web/src").rglob("*.tsx"))
    assert not (context / "web/test-results").exists()
    assert not (context / "web/node_modules").exists()
    assert not (context / ".local").exists()
    assert not (context / ".git").exists()
    removed = run_script(
        f". {ps_quote(ROOT / 'tools/docker-context.ps1')}; "
        f"Remove-DockerBuildContext {ps_quote(context)} {ps_quote(tmp_path)}"
    )
    assert removed.returncode == 0, removed.stderr
    assert not context.exists()


def test_cleanup_refuses_unrelated_directory(tmp_path: Path) -> None:
    unrelated = tmp_path / "keep"
    unrelated.mkdir()
    result = run_script(
        "$ErrorActionPreference = 'Stop'; "
        f". {ps_quote(ROOT / 'tools/docker-context.ps1')}; "
        f"Remove-DockerBuildContext {ps_quote(unrelated)} {ps_quote(tmp_path)}"
    )
    assert result.returncode != 0
    assert unrelated.is_dir()
