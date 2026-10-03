"""Command line: ``openblindysir-server [serve] [--host H] [--port P]`` and ``gen-secrets``."""

import argparse
import json
import secrets
import sys
from pathlib import Path

from openblindysir_server.auth.bridges import BridgeCredentials, valid_id
from openblindysir_server.config import ConfigError, load_settings
from openblindysir_server.logging import get, log_event, setup_logging
from openblindysir_server.private_files import create_private_file, require_unlinked_path

# Easy to dictate over a voice chat: no ambiguous letters (i, l, o).
DICTATABLE = "abcdefghjkmnpqrstuvwxyz"
EXIT_CONFIG = 2


def dictatable_password() -> str:
    """Four groups of four letters, e.g. ``kpzr-mtxe-qawn-dvhs`` (about 72 bits)."""
    return "-".join("".join(secrets.choice(DICTATABLE) for _ in range(4)) for _ in range(4))


def gen_secrets() -> str:
    blind = dictatable_password()
    host = dictatable_password()
    while host == blind:
        host = dictatable_password()
    return (
        f"BLIND_PASSWORD={blind}\nHOST_PASSWORD={host}\nBRIDGE_SECRET={secrets.token_urlsafe(32)}\n"
    )


def serve(host: str | None, port: int | None) -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        for var, reason in exc.problems:
            print(f"config_error var={var} reason={reason}", file=sys.stderr)
        return EXIT_CONFIG
    setup_logging(settings.log_level, settings.log_format, settings.secrets)
    log = get("server")
    for var, reason in settings.warnings:
        log_event(log, "config_warning", var=var, reason=reason)
    import uvicorn  # noqa: PLC0415 - only needed to serve

    from openblindysir_server.main import create_app  # noqa: PLC0415

    uvicorn.run(
        create_app(settings),
        host=host or settings.host,
        port=port or settings.port,
        workers=1,
        proxy_headers=False,
        ws_max_size=65_536,
        log_config=None,
        server_header=False,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="openblindysir-server", description="OpenBlindySir Server"
    )
    sub = parser.add_subparsers(dest="command")
    serve_parser = sub.add_parser("serve", help="run the server (default)")
    serve_parser.add_argument("--host")
    serve_parser.add_argument("--port", type=int)
    sub.add_parser("gen-secrets", help="print fresh secrets in .env format")
    provision = sub.add_parser(
        "bridge-credential", help="create or rotate an UUID-bound secret into a private TOML file"
    )
    provision.add_argument("--bridge-id", required=True)
    provision.add_argument("--name", default="Bridge")
    provision.add_argument("--output", type=Path, required=True)
    revoke_parser = sub.add_parser("bridge-revoke", help="revoke an UUID-bound credential")
    revoke_parser.add_argument("--bridge-id", required=True)
    args = parser.parse_args(argv)
    if args.command == "gen-secrets":
        sys.stdout.write(gen_secrets())
        return 0
    if args.command in {"bridge-credential", "bridge-revoke"}:
        try:
            settings = load_settings()
            identity = valid_id(args.bridge_id)
            if settings.state_dir is None:
                raise ValueError("persistent STATE_DIR required")
            registry = BridgeCredentials(
                settings.state_dir / "bridge-credentials.json",
                settings.bridge_secret,
                settings.bridge_secrets,
            )
            if args.command == "bridge-revoke":
                if not registry.revoke(identity):
                    raise ValueError("unknown Bridge identity")
            else:
                from openblindysir_protocol.text import normalize_nickname  # noqa: PLC0415

                name = normalize_nickname(args.name)
                require_unlinked_path(args.output)
                if args.output.resolve() in {
                    (settings.state_dir / filename).resolve()
                    for filename in (
                        "bridge-credentials.json",
                        "bridge-credentials.lock",
                        "session.json",
                        "session.previous.json",
                    )
                }:
                    raise ValueError("credential output is a managed state file")
                if args.output.exists():
                    raise ValueError("credential output already exists")
                args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                raw = secrets.token_urlsafe(32)
                body = (
                    f"bridge_id = {json.dumps(identity)}\n"
                    f"name = {json.dumps(name, ensure_ascii=False)}\n"
                    f"secret = {json.dumps(raw)}\n"
                )
                create_private_file(args.output, body.encode("utf-8"))
                try:
                    registry.replace(identity, name, raw)
                except BaseException:
                    args.output.unlink(missing_ok=True)
                    raise
            print(f"Bridge {identity}: {args.command} OK")
            return 0
        except (ConfigError, OSError, ValueError):
            print(
                "Bridge credential action failed; check configuration, UUID "
                "and private file permissions, or retry a concurrent credential change.",
                file=sys.stderr,
            )
            return EXIT_CONFIG
    return serve(getattr(args, "host", None), getattr(args, "port", None))
