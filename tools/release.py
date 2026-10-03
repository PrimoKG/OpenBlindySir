"""Version consistency, artifact provenance and release checks (no publication)."""

import argparse
import hashlib
import json
import re
import stat
import subprocess
import tarfile
import tomllib
import unicodedata
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("protocol", "server", "bridge")
TARGETS = {("windows", "x86_64"), ("linux", "x86_64"), ("macos", "x86_64"), ("macos", "arm64")}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def metadata() -> dict[str, object]:
    from openblindysir_protocol.version import PROTOCOL_VERSION  # noqa: PLC0415

    return {
        "version": ROOT.joinpath("VERSION").read_text().strip(),
        "protocol": PROTOCOL_VERSION,
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
    }


def set_version(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:rc\d+|\.dev\d+)?", version):
        raise ValueError("use X.Y.Z, X.Y.ZrcN or X.Y.Z.devN")
    ROOT.joinpath("VERSION").write_text(version + "\n", encoding="utf-8")
    for package in PACKAGES:
        ROOT.joinpath(package, "src", f"openblindysir_{package}", "_version.py").write_text(
            f'__version__ = "{version}"\n', encoding="utf-8"
        )
        if package in {"bridge", "server"}:
            path = ROOT / package / "pyproject.toml"
            text = re.sub(
                r'openblindysir-protocol==[^"\s]+',
                f"openblindysir-protocol=={version}",
                path.read_text(),
            )
            path.write_text(text, encoding="utf-8")


def verify_version(tag: str | None = None, *, clean: bool = False) -> dict[str, object]:
    data = metadata()
    version = str(data["version"])
    for package in PACKAGES:
        text = ROOT.joinpath(package, "src", f"openblindysir_{package}", "_version.py").read_text()
        if f'__version__ = "{version}"' not in text:
            raise ValueError(f"version mismatch: {package}")
        spec = tomllib.loads(ROOT.joinpath(package, "pyproject.toml").read_text())
        if (
            package != "protocol"
            and f"openblindysir-protocol=={version}" not in spec["project"]["dependencies"]
        ):
            raise ValueError(f"protocol dependency mismatch: {package}")
        if ROOT.joinpath(package, "LICENSE").read_bytes() != ROOT.joinpath("LICENSE").read_bytes():
            raise ValueError(f"license mismatch: {package}")
    if tag:
        match = re.fullmatch(r"v(\d+\.\d+\.\d+)(?:-rc\.(\d+))?", tag)
        expected = match[1] + (f"rc{match[2]}" if match[2] else "") if match else None
        if expected != version:
            raise ValueError("tag does not match VERSION (vX.Y.Z or vX.Y.Z-rc.N)")
        if git("rev-list", "-n", "1", tag) != data["commit"]:
            raise ValueError("tag does not identify this commit")
        if f"## [{version}]" not in ROOT.joinpath("CHANGELOG.md").read_text():
            raise ValueError("add the version's CHANGELOG entry before tagging")
    if clean and data["dirty"]:
        raise ValueError("release artifacts require a clean checkout")
    return data


def python_manifest(directory: Path) -> None:
    data = verify_version()
    files = sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz")])
    if {path.name for path in files} != python_filenames(str(data["version"])):
        raise ValueError("expected Bridge + protocol wheels and source distributions")
    for path in files:
        check_python(path, str(data["version"]))
    data["files"] = {path.name: sha256(path) for path in files}
    directory.joinpath("python-provenance.json").write_text(json.dumps(data, indent=2) + "\n")


def check_python(path: Path, version: str) -> None:
    if path.name not in python_filenames(version):
        raise ValueError("invalid Python artifact filename")
    package = path.name.split("-", 1)[0]
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            check_zip_members(archive)
            names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if names != [f"{package}-{version}.dist-info/METADATA"]:
                raise ValueError("invalid Python metadata name")
            name = names[0]
            row = BytesParser().parsebytes(archive.read(name))
    else:
        with tarfile.open(path) as archive:
            members = []
            total = 0
            for member in archive:
                total += member.size
                if (
                    len(members) >= 10000
                    or member.size > 128 * 1024 * 1024
                    or total > 512 * 1024 * 1024
                ):
                    raise ValueError("source archive too large")
                members.append(member)
            if any(
                not safe_archive_name(m.name)
                or private_archive_name(m.name)
                or not (m.isfile() or m.isdir())
                for m in members
            ):
                raise ValueError("unsafe source archive path")
            check_unique_paths([m.name for m in members])
            info = [m for m in members if m.name.count("/") == 1 and m.name.endswith("PKG-INFO")]
            if len(info) != 1 or info[0].name != f"{package}-{version}/PKG-INFO":
                raise ValueError("invalid Python metadata name")
            member = info[0]
            if member.size > 1024 * 1024:
                raise ValueError("source metadata too large")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("missing source metadata")
            row = BytesParser().parsebytes(stream.read())
    if row["Version"] != version or row["Name"] != package.replace("_", "-"):
        raise ValueError("invalid Python artifact version/name")
    if row[
        "Name"
    ] == "openblindysir-bridge" and f"openblindysir-protocol=={version}" not in row.get_all(
        "Requires-Dist", []
    ):
        raise ValueError("Bridge artifact has an unpinned protocol")


def python_filenames(version: str) -> set[str]:
    return {
        f"openblindysir_{package}-{version}{suffix}"
        for package in ("bridge", "protocol")
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    }


def safe_archive_name(name: str) -> bool:
    parts = name.removesuffix("/").split("/")
    return (
        bool(name)
        and not any(char in name for char in '\\:<>"|?*')
        and not any(unicodedata.category(char) in {"Cc", "Cf"} for char in name)
        and all(
            part not in {"", ".", ".."}
            and not part.endswith((".", " "))
            and not re.fullmatch(
                r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]",
                part.split(".", 1)[0],
                re.IGNORECASE,
            )
            for part in parts
        )
    )


def check_unique_paths(names: list[str]) -> None:
    normalized = [unicodedata.normalize("NFC", name.rstrip("/")).casefold() for name in names]
    if len(normalized) != len(set(normalized)):
        raise ValueError("duplicate or ambiguous archive path")


def private_archive_name(name: str) -> bool:
    return (
        PurePosixPath(name)
        .name.lower()
        .startswith(("config.toml", ".env", ".config-", "bridge-credentials", "credentials.toml"))
    )


def check_zip_members(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    if len(members) > 10000 or sum(m.file_size for m in members) > 512 * 1024 * 1024:
        raise ValueError("archive too large")
    if any(
        not safe_archive_name(m.filename)
        or private_archive_name(m.filename)
        or m.file_size > 128 * 1024 * 1024
        or stat.S_IFMT(m.external_attr >> 16) not in {0, stat.S_IFREG, stat.S_IFDIR}
        for m in members
    ):
        raise ValueError("private file or unsafe archive path/type")
    check_unique_paths([m.filename for m in members])


def check_binary(
    archive: zipfile.ZipFile, data: dict[str, object], *, clean: bool
) -> tuple[str, str]:
    names = archive.namelist()
    check_zip_members(archive)
    if any(
        private_archive_name(name)
        or PurePosixPath(name).name.lower() in {"ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"}
        for name in names
    ):
        raise ValueError("private configuration/tool or unsafe path in binary archive")
    manifests = [name for name in names if name.endswith("/release.json")]
    if len(manifests) != 1:
        raise ValueError("expected one binary manifest")
    manifest_name = manifests[0]
    manifest = json.loads(archive.read(manifest_name))
    if (
        any(manifest[key] != data[key] for key in ("version", "protocol", "commit"))
        or (clean and manifest["dirty"])
        or manifest.get("ffmpeg_included") is not False
    ):
        raise ValueError("binary provenance mismatch")
    prefix = manifest_name.removesuffix("release.json")
    target = (manifest["os"], manifest["arch"])
    if target not in TARGETS or prefix != (
        f"OpenBlindySir-Bridge-{data['version']}-{target[0]}-{target[1]}/"
    ):
        raise ValueError("binary target/name mismatch")
    if set(names) != {prefix + name for name in manifest["files"]} | {manifest_name}:
        raise ValueError("unlisted binary content")
    for name, expected in manifest["files"].items():
        if not safe_archive_name(name):
            raise ValueError("unsafe binary manifest path")
        if hashlib.sha256(archive.read(prefix + name)).hexdigest() != expected:
            raise ValueError("binary content checksum mismatch")
    return manifest["os"], manifest["arch"]


def collect(directory: Path, *, tag: str | None = None, clean: bool = False) -> None:
    data = verify_version(tag, clean=clean)
    version = str(data["version"])
    binary_names = {
        f"OpenBlindySir-Bridge-{version}-{system}-{arch}.zip" for system, arch in TARGETS
    }
    allowed = (
        python_filenames(version)
        | binary_names
        | {n + ".sha256" for n in binary_names}
        | {"python-provenance.json", "SHA256SUMS", "release-manifest.json", "release-notes.md"}
    )
    if any(
        p.name not in allowed or not p.is_file() or p.is_symlink() or p.is_junction()
        for p in directory.iterdir()
    ):
        raise ValueError("unexpected or linked file in release directory")
    if any(not p.with_suffix("").is_file() for p in directory.glob("*.zip.sha256")):
        raise ValueError("orphan binary checksum sidecar")
    provenance = json.loads(directory.joinpath("python-provenance.json").read_text())
    actual_python = {p.name for p in [*directory.glob("*.whl"), *directory.glob("*.tar.gz")]}
    if actual_python != python_filenames(version) or set(provenance["files"]) != actual_python:
        raise ValueError("Python artifact set mismatch")
    if any(provenance.get(key) != data[key] for key in ("commit", "version", "protocol")) or (
        clean and provenance["dirty"]
    ):
        raise ValueError("Python provenance mismatch")
    for name, expected in provenance["files"].items():
        if Path(name).name != name:
            raise ValueError("unsafe artifact filename")
        path = directory / name
        if sha256(path) != expected:
            raise ValueError("Python artifact checksum mismatch")
        check_python(path, version)
    found = set()
    for path in directory.glob("OpenBlindySir-Bridge-*.zip"):
        with zipfile.ZipFile(path) as archive:
            target = check_binary(archive, data, clean=clean)
            if target not in TARGETS or target in found:
                raise ValueError("unexpected/duplicate binary target")
            found.add(target)
            expected_name = f"OpenBlindySir-Bridge-{version}-{target[0]}-{target[1]}.zip"
            if path.name != expected_name:
                raise ValueError("binary filename/target mismatch")
        sidecar = path.with_name(path.name + ".sha256")
        if not sidecar.is_file() or sidecar.read_text().strip() != f"{sha256(path)}  {path.name}":
            raise ValueError("binary sidecar checksum mismatch")
    if clean and found != TARGETS:
        raise ValueError("all four native binary targets are required for publication")
    files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.name not in {"SHA256SUMS", "release-manifest.json", "release-notes.md"}
    )
    data["files"] = {path.name: sha256(path) for path in files}
    directory.joinpath("release-manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    files.append(directory / "release-manifest.json")
    directory.joinpath("SHA256SUMS").write_text(
        "".join(f"{sha256(p)}  {p.name}\n" for p in sorted(files)), encoding="utf-8"
    )
    directory.joinpath("release-notes.md").write_text(
        f"OpenBlindySir {version} · protocol {data['protocol']}\n\nCommit: `{data['commit']}`.\n\n"
        "Bridge archives exclude FFmpeg. See the installation and troubleshooting guides. "
        "Verify SHA256SUMS before launching. Binaries are unsigned and not notarized.\n\n"
        "See CHANGELOG.md at this tag for the release changes.\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["set-version", "verify", "python-manifest", "collect"])
    parser.add_argument("--version")
    parser.add_argument("--tag")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--directory", type=Path, default=ROOT / "dist")
    ns = parser.parse_args()
    if ns.command == "set-version":
        if not ns.version:
            parser.error("--version required")
        set_version(ns.version)
    elif ns.command == "verify":
        print(json.dumps(verify_version(ns.tag, clean=ns.require_clean), indent=2))
    elif ns.command == "python-manifest":
        python_manifest(ns.directory)
    else:
        collect(ns.directory, tag=ns.tag, clean=ns.require_clean)


if __name__ == "__main__":
    main()
