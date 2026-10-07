"""Create a local, versioned offline Docker pack after validation; never publish it."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--bridge", required=True)
    parser.add_argument("--caddy", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", args.version):
        parser.error("Version must be a simple release identifier")
    for reference in (args.server, args.bridge, args.caddy):
        if not re.fullmatch(
            r"[a-z0-9][a-z0-9./_-]*(?::[A-Za-z0-9._-]+|@sha256:[a-f0-9]{64})", reference
        ):
            parser.error("Images must use explicit tags or SHA-256 digests")
    target = args.output.resolve()
    if not target.is_relative_to(ROOT / ".local") or target.exists():
        parser.error("Output must be a fresh directory inside .local")
    target.mkdir(parents=True)
    manifest = {"version": args.version, "signed": False, "images": {}}
    for service, reference in [
        ("app", args.server),
        ("bridge", args.bridge),
        ("caddy", args.caddy),
    ]:
        info = json.loads(run("image", "inspect", reference))[0]
        if service != "caddy":
            protocol = run(
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--entrypoint",
                "python",
                reference,
                "-c",
                "from openblindysir_protocol.version import PROTOCOL_VERSION; "
                "print(PROTOCOL_VERSION)",
            )
            if protocol != "10":
                raise ValueError("Incompatible image protocol")
        manifest["images"][service] = {
            "reference": reference,
            "id": info["Id"],
            "platform": f"{info['Os']}/{info['Architecture']}",
        }
    subprocess.run(
        [
            "docker",
            "image",
            "save",
            "--output",
            str(target / "images.tar"),
            args.server,
            args.bridge,
            args.caddy,
        ],
        check=True,
    )
    for relative in [
        "tools/docker-host.ps1",
        "tools/docker-host.sh",
        "tools/docker-context.ps1",
        "tools/file-integrity.ps1",
        "tools/private-config.ps1",
        "tools/restore_pack_state.py",
        "tools/party-assistant.ps1",
        "tools/pack-maintenance.ps1",
        "deploy/compose.public.yaml",
        "tools/load-pack.ps1",
        "tools/load-pack.sh",
        "deploy/Caddyfile.docker.private",
        "deploy/Caddyfile.docker.public",
        "docs/certificat-local.md",
        "docs/local-certificate.en.md",
        "docs/offline-pack.md",
        "docs/offline-pack.en.md",
        "docs/audits/2026-10-07-implementation.md",
        "docs/audits/2026-10-07-implementation.en.md",
        "docs/audits/2026-10-08-autofix.md",
        "docs/audits/2026-10-08-autofix.en.md",
        "LICENSE",
    ]:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    compose = compose.replace("image: openblindysir-server:local", f"image: {args.server}")
    compose = compose.replace("image: openblindysir-bridge:local", f"image: {args.bridge}")
    compose = compose.replace("image: openblindysir-caddy:local", f"image: {args.caddy}")
    # docker-host init uses this local name for the config wizard only.
    manifest["wizard_alias"] = args.server
    (target / "images.list").write_text(
        "\n".join(
            f"{service} {item['reference']} {item['id']}"
            for service, item in manifest["images"].items()
        )
        + "\n",
        encoding="ascii",
        newline="\n",
    )
    (target / "compose.yaml").write_text(compose, encoding="utf-8", newline="\n")
    (target / "README.md").write_text(
        "# OpenBlindySir — local candidate / candidat local\n\n"
        "Unsigned Linux/amd64 pack. Open security findings remain; read the audit first.\n\n"
        "Pack Linux/amd64 non signé. Alertes de sécurité restantes : lire le rapport.\n\n"
        "- [Audit FR](docs/audits/2026-10-08-autofix.md) / "
        "[Audit EN](docs/audits/2026-10-08-autofix.en.md)\n"
        "- [Installation FR](docs/offline-pack.md) / [Installation EN](docs/offline-pack.en.md)\n\n"
        "Windows: `powershell -File .\\tools\\load-pack.ps1`, then / puis "
        "`powershell -File .\\tools\\party-assistant.ps1`.\n\n"
        "Linux/macOS: `sh tools/load-pack.sh`, then follow the guide / suivre le guide.\n",
        encoding="utf-8",
    )
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    hashes = []
    for path in sorted(target.rglob("*")):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        hashes.append(f"{digest}  {path.relative_to(target).as_posix()}")
    (target / "SHA256SUMS").write_text("\n".join(hashes) + "\n", encoding="ascii", newline="\n")
    print(f"Offline pack created: {target}")


if __name__ == "__main__":
    main()
