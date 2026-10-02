"""Generate private Compose configuration inside the image; no host Python required."""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from host_pc import HostingError, address_for_mode
from openblindysir_server.cli import gen_secrets


def dotenv_quote(value: str) -> str:
    if any(c in value for c in "\r\n\x00"):
        raise HostingError("Le chemin doit tenir sur une ligne.")
    # Compose single quotes preserve dollar signs in personal folder names.
    return "'" + value.replace("'", "\\'") + "'"


def write_docker_config(
    path: Path, *, address: str, mode: str, music_dir: str, demo: bool = False
) -> None:
    authority, bind = address_for_mode(address, mode)
    parts = urlsplit(f"https://{authority}")
    host = parts.hostname or ""
    tls_host = f"[{host}]" if ":" in host else host
    port = parts.port or 443
    bind_ip = bind if mode == "private" else "0.0.0.0"  # noqa: S104 - public proxy ports only
    if not music_dir:
        raise HostingError("Choisissez un dossier musical existant.")
    body = (
        "# Private Docker configuration. Never commit or share this file.\n"
        + gen_secrets()
        + f"DOMAIN={authority}\nTLS_HOST={tls_host}\nHTTPS_PORT={port}\n"
        + f"BIND_IP={bind_ip}\nCADDY_PROFILE={mode}\n"
        + f"MUSIC_DIR={dotenv_quote(music_dir)}\nBRIDGE_DEMO={'true' if demo else 'false'}\n"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
        file.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Préparer le lancement Docker OpenBlindySir.")
    parser.add_argument("--address", required=True)
    parser.add_argument("--mode", choices=("private", "public"), default="private")
    parser.add_argument("--music-dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("/setup/hosting.env"))
    args = parser.parse_args()
    try:
        write_docker_config(
            args.output,
            address=args.address,
            mode=args.mode,
            music_dir=args.music_dir,
            demo=args.demo,
        )
    except (HostingError, OSError) as exc:
        print(f"Configuration Docker impossible : {exc}", file=sys.stderr)
        return 2
    print("Configuration privée créée. Consultez docs/docker.md pour la suite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
