"""Local offline Grype scans of immutable images; never mount the Docker socket or state."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from collections import Counter
from pathlib import Path

SCANNER = "anchore/grype@sha256:5c88961f4130e830542d441c7ed6c78baa28e799163abac53d2be4923fb5ab7d"


def run(command: list[str]) -> bytes:
    return subprocess.run(command, check=True, capture_output=True).stdout


def archive_config_id(path: Path) -> str:
    with tarfile.open(path) as archive:
        member = archive.extractfile("manifest.json")
        if member is None:
            raise ValueError("Missing image manifest")
        manifest = json.load(member)
        if len(manifest) != 1:
            raise ValueError("Expected exactly one image")
        config = archive.extractfile(manifest[0]["Config"])
        if config is None:
            raise ValueError("Missing image config")
        return "sha256:" + hashlib.sha256(config.read()).hexdigest()


def validate_ffmpeg_component(sbom: dict, facts: dict) -> None:
    components = [c for c in sbom["components"] if c["name"] == "ffmpeg"]
    if len(components) != 1 or components[0]["version"] != facts["version"]:
        raise ValueError("FFmpeg SBOM does not match image version")
    if {"alg": "SHA-256", "content": facts["sha256"]} not in components[0]["hashes"]:
        raise ValueError("FFmpeg SBOM does not match corresponding source")


def scan(docker: list[str], target: str, result: str, directory: Path, cache: Path) -> dict:
    command = [
        *docker,
        "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--env", "GRYPE_DB_CACHE_DIR=/cache",
        "--env", "GRYPE_DB_AUTO_UPDATE=false",
        "--env", "GRYPE_CHECK_FOR_APP_UPDATE=false",
        "--env", "SYFT_CACHE_DIR=/tmp/syft",
    ]  # fmt: skip
    for source, destination, readonly in (
        (directory / "temporary", "/tmp", False),  # noqa: S108 - isolated scanner mount destination
        (cache, "/cache", True),
        (directory / "input", "/scan", True),
        (directory / "output", "/results", False),
    ):
        command += [
            "--mount",
            f"type=bind,source={source},target={destination}" + (",readonly" if readonly else ""),
        ]
    run([*command, SCANNER, target, "--output", "json", "--file", f"/results/{result}.json"])
    return json.loads((directory / "output" / f"{result}.json").read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", required=True, help="label=image-reference")
    parser.add_argument("--cache", type=Path, required=True, help="Pre-downloaded Grype DB")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--docker-config", type=Path)
    parser.add_argument("--ffmpeg-sbom", type=Path, help="Supplement for compiled FFmpeg")
    parser.add_argument(
        "--ffmpeg-image", default="bridge", help="Image label owning compiled FFmpeg"
    )
    args = parser.parse_args()
    directory = args.output.resolve()
    cache = args.cache.resolve(strict=True)
    for name in ("input", "output", "temporary"):
        (directory / name).mkdir(parents=True, exist_ok=True)
    docker = ["docker"]
    if args.docker_config:
        docker += ["--config", str(args.docker_config.resolve(strict=True))]
    summary = {"scanner": SCANNER, "images": {}}
    for value in args.image:
        label, separator, reference = value.partition("=")
        if not separator or not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", label) or not reference:
            parser.error("Each image must have a simple unique label and reference")
        if label in summary["images"]:
            parser.error("Duplicate image label")
        image_id = (
            run([*docker, "image", "inspect", "--format", "{{.Id}}", reference]).decode().strip()
        )
        archive = directory / "input" / f"{label}.tar"
        run([*docker, "image", "save", "--output", str(archive), image_id])
        config_id = archive_config_id(archive)
        data = scan(docker, f"docker-archive:/scan/{label}.tar", label, directory, cache)
        if data["source"]["target"]["imageID"] != config_id:
            raise ValueError("Scan does not match image config")
        summary["images"][label] = {
            "reference": reference,
            "image_id": image_id,
            "config_id": config_id,
            "scan_sha256": hashlib.sha256(
                (directory / "output" / f"{label}.json").read_bytes()
            ).hexdigest(),
            "counts": dict(Counter(m["vulnerability"]["severity"] for m in data["matches"])),
            "db": data["descriptor"]["db"]["status"],
        }
        print(f"{label}: offline scan verified against immutable image", flush=True)
    if args.ffmpeg_sbom:
        if args.ffmpeg_image not in summary["images"]:
            parser.error("The compiled FFmpeg supplement needs its scanned image label")
        owner = summary["images"][args.ffmpeg_image]["image_id"]
        # Bind the manually declared component to the exact binary/source in that image.
        inspect_code = (
            "import hashlib,json,re,subprocess;from pathlib import Path;"
            "output=subprocess.check_output(['/usr/local/bin/ffmpeg','-version']).decode();"
            "version=re.search(r'version n?([0-9.]+)',output).group(1);"
            "source=Path('/usr/local/share/licenses/ffmpeg/source.tar.xz').read_bytes();"
            "print(json.dumps({'version':version,'sha256':hashlib.sha256(source).hexdigest()}))"
        )
        facts = json.loads(
            run(
                [
                    *docker,
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--entrypoint",
                    "python",
                    owner,
                    "-c",
                    inspect_code,
                ]
            )
        )
        sbom = json.loads(args.ffmpeg_sbom.read_text(encoding="utf-8"))
        validate_ffmpeg_component(sbom, facts)
        (directory / "input" / "compiled-ffmpeg.cdx.json").write_bytes(
            args.ffmpeg_sbom.read_bytes()
        )
        data = scan(
            docker, "sbom:/scan/compiled-ffmpeg.cdx.json", "compiled-ffmpeg", directory, cache
        )
        summary["compiled_ffmpeg"] = {
            "image_id": owner,
            "verified_component": facts,
            "sbom_sha256": hashlib.sha256(args.ffmpeg_sbom.read_bytes()).hexdigest(),
            "counts": dict(Counter(m["vulnerability"]["severity"] for m in data["matches"])),
        }
        print("Compiled FFmpeg supplementary scan completed", flush=True)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
