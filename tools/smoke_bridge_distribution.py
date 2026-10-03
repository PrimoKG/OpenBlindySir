"""Smoke a delivered archive or isolated uvx wheel outside any checkout."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from release import check_binary, check_zip_members, sha256


def extract(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as zipped:
        check_zip_members(zipped)
        manifests = [n for n in zipped.namelist() if n.endswith("/release.json")]
        if len(manifests) != 1:
            raise ValueError("expected one binary manifest")
        check_binary(zipped, json.loads(zipped.read(manifests[0])), clean=False)
        for item in zipped.infolist():
            path = destination.joinpath(item.filename).resolve()
            if not path.is_relative_to(destination) or "\\" in item.filename:
                raise ValueError("unsafe archive path")
            zipped.extract(item, destination)
            if os.name == "posix" and not item.is_dir():
                path.chmod((item.external_attr >> 16) & 0o777)
    (manifest,) = destination.glob("*/release.json")
    data = json.loads(manifest.read_text())
    assert data["ffmpeg_included"] is False
    for name, expected in data["files"].items():
        path = (manifest.parent / name).resolve()
        assert path.is_relative_to(manifest.parent)
        assert sha256(path) == expected, name
    return manifest.parent / (
        "openblindysir-bridge.exe" if os.name == "nt" else "openblindysir-bridge"
    )


def smoke(program: list[str], directory: Path, version: str) -> None:
    secret = "SYNTHETIC-DISTRIBUTION-TEST-" + "x" * 32
    music = directory / "music"
    music.mkdir()
    config = directory / "config.toml"
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENBLINDYSIR_BRIDGE_")}
    env.update(
        OPENBLINDYSIR_BRIDGE_SERVER="https://example.com",
        OPENBLINDYSIR_BRIDGE_DIR=str(music),
        OPENBLINDYSIR_BRIDGE_NAME="Synthetic",
        OPENBLINDYSIR_BRIDGE_SECRET=secret,
        PYTHONIOENCODING="utf-8",
    )

    def run(*args: str, code: int = 0) -> str:
        result = subprocess.run(
            [*program, *args, "--config", str(config)],
            cwd=directory,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        output = result.stdout + result.stderr
        assert secret not in output
        assert str(music) not in output
        assert "Traceback" not in output
        assert result.returncode == code, f"{args}: exit {result.returncode}: {output[-2000:]}"
        return result.stdout

    assert version in run("--version")
    assert "doctor" in run("--help")
    assert not config.exists()
    run("check-ffmpeg")
    run("check-config")
    report = json.loads(run("doctor", "--json"))
    assert report["bridge_version"] == version
    assert report["connection"] == "not_checked"
    assert report["tracks"] is None
    assert not config.exists(), "read-only checks wrote configuration"
    credential = directory / "issued.toml"
    credential.write_text(
        'bridge_id = "12345678-1234-1234-1234-123456789abd"\n'
        'name = "Synthetic identity"\n'
        f"secret = {json.dumps(secret)}\n",
        encoding="utf-8",
    )
    env["OPENBLINDYSIR_BRIDGE_SECRET"] = "SYNTHETIC-STALE-ENV-" + "y" * 32
    run("check-config", "--credentials", str(credential))
    identity_report = json.loads(run("doctor", "--json", "--credentials", str(credential)))
    assert identity_report["connection"] == "not_checked"
    credential.write_text('name = "Incomplete identity"\n', encoding="utf-8")
    run("check-config", "--credentials", str(credential), code=2)
    env["OPENBLINDYSIR_BRIDGE_SECRET"] = secret
    config.write_text(f"secret = {secret}\n", encoding="utf-8")
    run("check-config", code=2)
    print(f"PASS {version}: help, version, FFmpeg, credentials, redacted doctor, bad config")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--wheels", type=Path)
    parser.add_argument("--uv", default=shutil.which("uv"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--version", required=True)
    ns = parser.parse_args()
    if bool(ns.archive) == bool(ns.wheels):
        parser.error("choose --archive or --wheels")
    with tempfile.TemporaryDirectory(prefix="openblindysir-distribution-") as folder:
        directory = Path(folder).resolve()
        if ns.archive:
            program = [str(extract(ns.archive.resolve(), directory))]
        else:
            if not ns.uv:
                parser.error("uv is required")
            wheels = ns.wheels.resolve()
            (wheel,) = wheels.glob("openblindysir_bridge-*.whl")
            program = [
                ns.uv,
                "tool",
                "run",
                "--isolated",
                "--no-config",
                "--no-env-file",
                "--python",
                ns.python,
                "--from",
                str(wheel),
                "--find-links",
                str(wheels),
                "openblindysir-bridge",
            ]
        smoke(program, directory, ns.version)


if __name__ == "__main__":
    main()
