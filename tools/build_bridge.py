"""Build a native PyInstaller onedir ZIP. Does not publish or bundle FFmpeg."""

import argparse
import datetime
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from packaging.requirements import Requirement

from release import ROOT, TARGETS, git, sha256, verify_version


def runtime_dependencies() -> list[importlib.metadata.Distribution]:
    found = {}
    waiting = ["openblindysir-bridge", "pyinstaller"]
    while waiting:
        name = waiting.pop()
        dist = importlib.metadata.distribution(name)
        canonical = dist.metadata["Name"].lower().replace("_", "-")
        if canonical in found:
            continue
        found[canonical] = dist
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                waiting.append(req.name)
    return [found[key] for key in sorted(found)]


def require_runtime_versions(version: str) -> None:
    """Refuse stale editable metadata before building a misleading manifest."""
    for package in ("openblindysir-bridge", "openblindysir-protocol"):
        if importlib.metadata.version(package) != version:
            raise ValueError(f"{package} installation is stale; reinstall it from this checkout")


def notices(directory: Path) -> dict[str, str]:
    destination = directory / "notices"
    destination.mkdir()
    lines = [
        "OpenBlindySir: LICENSE (MIT). FFmpeg is not included.",
        "PyInstaller bootloader: GPL with distribution exception; see its notices.",
    ]
    versions = {}
    for dist in runtime_dependencies():
        name = dist.metadata["Name"]
        versions[name] = dist.version
        license_paths = [
            f
            for f in dist.files or []
            if f.name.lower().startswith(("license", "copying", "notice"))
        ]
        for index, file in enumerate(license_paths):
            source = Path(str(dist.locate_file(file)))
            if source.is_file():
                shutil.copyfile(source, destination / f"{name}-{index}-{file.name}")
        expression = (
            dist.metadata.get("License-Expression")
            or dist.metadata.get("License")
            or "See included license files / upstream distribution."
        )
        lines.append(f"{name} {dist.version}: {expression}")
    candidates = [Path(sys.base_prefix) / name for name in ("LICENSE.txt", "LICENSE")]
    candidates += [
        Path(sys.base_prefix)
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "LICENSE.txt"
    ]
    python_license = next((path for path in candidates if path.is_file()), None)
    if python_license is None:
        raise ValueError("Python license missing; build using an official CPython installation")
    shutil.copyfile(python_license, destination / "Python-LICENSE.txt")
    directory.joinpath("THIRD_PARTY_NOTICES.txt").write_text(
        "\n\n".join(lines) + "\n", encoding="utf-8"
    )
    return versions


def build(output: Path) -> Path:
    data = verify_version()
    require_runtime_versions(str(data["version"]))
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}[platform.system()]
    arch = {"AMD64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}[
        platform.machine()
    ]
    if (system, arch) not in TARGETS:
        raise ValueError("unsupported native target; see bridge-installation.md")
    parent = ROOT / ".local" / "bridge-build"
    parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="build-", dir=parent)).resolve()
    try:
        argv = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onedir",
            "--console",
            "--noupx",
            "--name",
            "openblindysir-bridge",
            "--distpath",
            str(scratch / "dist"),
            "--workpath",
            str(scratch / "work"),
            "--specpath",
            str(scratch),
            "--collect-submodules",
            "websockets",
            "--collect-submodules",
            "openblindysir_protocol",
        ]
        for module in (
            "openblindysir_server",
            "fastapi",
            "uvicorn",
            "pytest",
            "hypothesis",
            "twine",
            "uv",
            "ruff",
            "rich",
            "pygments",
            "uvloop",
        ):
            argv += ["--exclude-module", module]
        argv.append(str(ROOT / "tools" / "bridge_entry.py"))
        subprocess.run(argv, cwd=ROOT, check=True)
        bundle = scratch / "dist" / "openblindysir-bridge"
        executable = bundle / (
            "openblindysir-bridge.exe" if system == "windows" else "openblindysir-bridge"
        )
        subprocess.run([str(executable), "--version"], cwd=scratch, check=True, timeout=20)
        subprocess.run(
            [str(executable), "--help"],
            cwd=scratch,
            check=True,
            timeout=20,
            stdout=subprocess.DEVNULL,
        )
        shutil.copyfile(ROOT / "LICENSE", bundle / "LICENSE")
        shutil.copyfile(ROOT / "SECURITY.md", bundle / "SECURITY.md")
        shutil.copyfile(ROOT / "VERSION", bundle / "VERSION")
        shutil.copyfile(ROOT / "docs" / "bridge-binary-start.txt", bundle / "README.txt")
        guides = bundle / "docs"
        guides.mkdir()
        for name in (
            "bridge-installation.md",
            "bridge-installation.en.md",
            "troubleshooting.md",
            "operations.md",
            "operations.en.md",
            "releasing.md",
            "deployment.md",
            "docker.md",
            "media-and-metadata.md",
            "guide-utilisateur.md",
            "user-guide.en.md",
            "bridge-security.md",
            "v0.5.md",
            "v0.5.en.md",
        ):
            shutil.copyfile(ROOT / "docs" / name, guides / name)
        data.update(
            os=system,
            arch=arch,
            python=platform.python_version(),
            ffmpeg_included=False,
            dependencies=notices(bundle),
        )
        data["files"] = {
            path.relative_to(bundle).as_posix(): sha256(path)
            for path in sorted(bundle.rglob("*"))
            if path.is_file()
        }
        bundle.joinpath("release.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        output.mkdir(parents=True, exist_ok=True)
        stem = f"OpenBlindySir-Bridge-{data['version']}-{system}-{arch}"
        archive = output / f"{stem}.zip"
        timestamp = datetime.datetime.fromtimestamp(
            max(315532800, int(git("log", "-1", "--format=%ct"))), datetime.UTC
        )
        with zipfile.ZipFile(
            archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as zipped:
            for path in sorted(bundle.rglob("*")):
                if not path.is_file():
                    continue
                item = zipfile.ZipInfo(
                    stem + "/" + path.relative_to(bundle).as_posix(), timestamp.timetuple()[:6]
                )
                item.compress_type = zipfile.ZIP_DEFLATED
                item.create_system = 3
                item.external_attr = (0o100000 | (path.stat().st_mode & 0o755)) << 16
                zipped.writestr(item, path.read_bytes())
        output.joinpath(f"{stem}.zip.sha256").write_text(
            f"{sha256(archive)}  {archive.name}\n", encoding="utf-8"
        )
        print(f"Built {archive.name}; FFmpeg excluded. Provenance is in release.json.")
        return archive
    finally:
        # Only our freshly created scratch directory under the verified workspace root.
        if (
            scratch.parent == parent.resolve()
            and scratch.name.startswith("build-")
            and not os.path.isjunction(scratch)
        ):
            shutil.rmtree(scratch)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "binary")
    build(parser.parse_args().output.resolve())
