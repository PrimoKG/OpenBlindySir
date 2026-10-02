"""Run the existing single-process server and Caddy on a personal computer."""

import argparse
import ipaddress
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from openblindysir_server.cli import gen_secrets
from openblindysir_server.config import ConfigError, load_settings, read_dotenv

ROOT = Path(__file__).resolve().parents[1]
MODES = ("private", "public")
DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.IGNORECASE)


class HostingError(ValueError):
    """An actionable setup error, without credentials or configuration values."""


def address_for_mode(address: str, mode: str) -> tuple[str, str]:
    """Return a canonical HTTPS authority and the private listening interface."""
    if mode not in MODES:
        raise HostingError("Mode attendu : private ou public.")
    try:
        parts = urlsplit(f"https://{address}")
        host = parts.hostname or ""
        port = 443 if parts.port is None else parts.port
    except ValueError as exc:
        raise HostingError(
            "Adresse invalide ; utilisez une IP ou un domaine, avec port facultatif."
        ) from exc
    if (
        not host
        or parts.netloc != address
        or parts.username is not None
        or parts.password is not None
        or parts.path
        or parts.query
        or parts.fragment
        or any(c.isspace() for c in address)
        or port < 1
        or "%" in host
    ):
        raise HostingError("Adresse sans https://, chemin, identifiants ni caractères spéciaux.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if mode == "private":
        if host != "localhost" and ip is None:
            raise HostingError("Mode privé : indiquez l'IP LAN/VPN du PC, ou localhost.")
        if ip is not None and (ip.is_unspecified or ip.is_multicast):
            raise HostingError("Indiquez l'IP d'une interface du PC, pas une adresse générique.")
    elif (
        ip is not None
        or host == "localhost"
        or "." not in host
        or not all(DNS_LABEL.fullmatch(label) for label in host.split("."))
        or port != 443
    ):
        raise HostingError("Mode public : un nom de domaine et le port HTTPS 443 sont requis.")
    authority = f"[{host}]" if ":" in host else host
    if port != 443:
        authority = f"{authority}:{port}"
    return authority, "127.0.0.1" if host == "localhost" else host


def init_config(path: Path, address: str, mode: str) -> None:
    authority, _ = address_for_mode(address, mode)
    body = (
        "# Private configuration; never commit or share this file.\n"
        + gen_secrets()
        + f"DOMAIN={authority}\nPC_HOSTING_MODE={mode}\n"
        + "DEV_MODE=0\nBIND_HOST=127.0.0.1\nPORT=8000\n"
        + "TRUSTED_PROXIES=127.0.0.1/32,::1/128\nSTATIC_DIR=web/dist\n"
        + "LOG_LEVEL=INFO\nLOG_TRACK_NAMES=false\n"
    )
    # Exclusive creation protects an existing party's passwords. UTF-8 without BOM
    # also works when the launcher is invoked from Windows PowerShell 5.1.
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(body)
    except FileExistsError as exc:
        raise HostingError(
            "Le fichier existe déjà : modifiez-le, ou choisissez --env-file."
        ) from exc


@dataclass(frozen=True)
class HostingPlan:
    env: dict[str, str]
    caddyfile: Path
    url: str
    mode: str
    root_certificate: Path


def hosting_plan(root: Path, values: Mapping[str, str], mode: str | None) -> HostingPlan:
    env = dict(values)
    chosen = mode or env.get("PC_HOSTING_MODE", "private")
    authority, bind = address_for_mode(env.get("DOMAIN", ""), chosen)
    if env.get("DEV_MODE", "0").lower() not in {"0", "false", "no"}:
        raise HostingError("Hébergement PC : gardez DEV_MODE=0 et HTTPS actif.")
    static = Path(env.get("STATIC_DIR") or root / "web" / "dist")
    static = (root / static).resolve() if not static.is_absolute() else static.resolve()
    if not (static / "index.html").is_file():
        raise HostingError(
            "Interface absente : lancez npm --prefix web ci puis npm --prefix web run build."
        )
    data = root / ".local" / "caddy"
    env.update(
        DOMAIN=authority,
        DEV_MODE="0",
        BIND_HOST="127.0.0.1",
        TRUSTED_PROXIES="127.0.0.1/32,::1/128",
        STATIC_DIR=str(static),
        OPENBLINDYSIR_CADDY_BIND=bind,
        OPENBLINDYSIR_CADDY_DATA=data.as_posix(),
    )
    settings = load_settings(env, dotenv=None)
    if settings.port == (urlsplit(f"https://{authority}").port or 443):
        raise HostingError("PORT (serveur interne) doit être différent du port HTTPS.")
    env["PORT"] = str(settings.port)
    return HostingPlan(
        env=env,
        caddyfile=root / "deploy" / f"Caddyfile.pc.{chosen}",
        url=f"https://{authority}",
        mode=chosen,
        root_certificate=data / "pki" / "authorities" / "local" / "root.crt",
    )


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_plan(plan: HostingPlan, caddy: str, *, check: bool = False) -> int:
    command = [caddy, "validate", "--config", str(plan.caddyfile), "--adapter", "caddyfile"]
    subprocess.run(command, env=plan.env, cwd=ROOT, check=True)
    if check:
        return 0
    print(f"Partie : {plan.url}\nHôte : {plan.url}/host", flush=True)
    if plan.mode == "private":
        print(f"Certificat racine à faire approuver sur les appareils : {plan.root_certificate}")
    print(
        "Gardez ce terminal ouvert. Ctrl+C arrête la partie et efface son état en mémoire.",
        flush=True,
    )
    processes: list[subprocess.Popen[bytes]] = []
    try:
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", "openblindysir_server", "serve"], env=plan.env, cwd=ROOT
            )
        )
        command[1] = "run"
        processes.append(subprocess.Popen(command, env=plan.env, cwd=ROOT))
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
        print("Un service s'est arrêté ; arrêt de l'autre service.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for process in reversed(processes):
            stop_process(process)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Héberger OpenBlindySir sur son PC avec HTTPS.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="créer une configuration et des secrets, sans écraser")
    init.add_argument("--address", required=True, help="IP LAN/VPN:port ou nom de domaine public")
    init.add_argument("--mode", choices=MODES, default="private")
    init.add_argument("--env-file", type=Path, default=ROOT / ".env")
    run = sub.add_parser("run", help="démarrer le serveur et Caddy")
    run.add_argument("--mode", choices=MODES, help="par défaut : PC_HOSTING_MODE du fichier")
    run.add_argument("--env-file", type=Path, default=ROOT / ".env")
    run.add_argument("--caddy", default="caddy", help="commande ou chemin du binaire Caddy")
    run.add_argument("--check", action="store_true", help="vérifier sans démarrer la partie")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init_config(args.env_file, args.address, args.mode)
            print(
                f"Configuration créée : {args.env_file}\n"
                "Consultez docs/deployment.md pour la suite."
            )
            return 0
        values = {**read_dotenv(args.env_file), **os.environ}
        plan = hosting_plan(ROOT, values, args.mode)
        caddy = shutil.which(args.caddy)
        if caddy is None:
            raise HostingError("Caddy introuvable : installez-le ou indiquez --caddy CHEMIN.")
        return run_plan(plan, caddy, check=args.check)
    except ConfigError as exc:
        for variable, reason in exc.problems:
            print(f"config_error var={variable} reason={reason}", file=sys.stderr)
        return 2
    except (HostingError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Hébergement impossible : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
