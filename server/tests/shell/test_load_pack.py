"""Verify pack integrity before any Docker command, including BSD utility coexistence."""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if os.name == "nt":
    git_bash = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Git/bin/bash.exe"
    SHELL = str(git_bash) if git_bash.is_file() else None
else:
    SHELL = shutil.which("sh")
pytestmark = pytest.mark.skipif(SHELL is None, reason="POSIX shell is unavailable")


def run_pack(pack: Path, actual_id: str) -> subprocess.CompletedProcess[str]:
    assert SHELL is not None
    env = dict(os.environ)
    env["PACK_TEST_LOG"] = (pack / "docker.log").as_posix()
    env["PACK_TEST_ID"] = actual_id
    # Git Bash provides the same real Perl shasum as macOS, outside its default PATH.
    prefix = 'PATH="/usr/bin:/bin:/usr/bin/core_perl:$PATH"; ' if os.name == "nt" else ""
    return subprocess.run(
        [
            SHELL,
            "-c",
            prefix + 'PATH="$(cd "$1" && pwd):$PATH"; export PATH; sh "$2"',
            "pack-test",
            (pack / "bin").as_posix(),
            (pack / "tools/load-pack.sh").as_posix(),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    (tmp_path / "tools").mkdir()
    shutil.copyfile(ROOT / "tools/load-pack.sh", tmp_path / "tools/load-pack.sh")
    (tmp_path / "bin").mkdir()
    (tmp_path / "images.tar").write_bytes(b"synthetic image archive")
    (tmp_path / "images.list").write_text(
        "app example:pack sha256:1234\n", encoding="ascii", newline="\n"
    )
    (tmp_path / "bin/docker").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$PACK_TEST_LOG"\n'
        'if [ "$1" = image ]; then printf "%s\\n" "$PACK_TEST_ID"; fi\n',
        encoding="ascii",
        newline="\n",
    )
    # Mirrors macOS having a sha256sum that rejects GNU --strict/--check flags.
    (tmp_path / "bin/sha256sum").write_text("#!/bin/sh\nexit 97\n", encoding="ascii")
    for tool in (tmp_path / "bin").iterdir():
        tool.chmod(0o700)
    lines = [
        f"{hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()}  {name}\n"
        for name in ("images.tar", "images.list", "tools/load-pack.sh")
    ]
    (tmp_path / "SHA256SUMS").write_text("".join(lines), encoding="ascii", newline="\n")
    return tmp_path


def test_loads_verified_pack_with_bsd_sha256sum_present(pack: Path) -> None:
    result = run_pack(pack, "sha256:1234")
    assert result.returncode == 0, result.stdout + result.stderr
    commands = (pack / "docker.log").read_text()
    assert "load --input images.tar" in commands
    assert "tag example:pack openblindysir-server:local" in commands


@pytest.mark.parametrize("damage", ["archive", "manifest"])
def test_invalid_pack_never_reaches_docker(pack: Path, damage: str) -> None:
    if damage == "archive":
        (pack / "images.tar").write_bytes(b"modified image archive")
    else:
        with (pack / "SHA256SUMS").open("a", encoding="ascii", newline="\n") as stream:
            stream.write("malformed checksum line\n")
    result = run_pack(pack, "sha256:1234")
    assert result.returncode != 0
    assert not (pack / "docker.log").exists()


def test_image_identity_mismatch_never_promotes_wizard_alias(pack: Path) -> None:
    result = run_pack(pack, "sha256:5678")
    assert result.returncode != 0
    commands = (pack / "docker.log").read_text()
    assert "load --input images.tar" in commands
    assert "tag " not in commands
