"""Command line: ``openblindysir-server [serve] [--host H] [--port P]`` and ``gen-secrets``."""

import argparse
import secrets
import sys

from openblindysir_server.config import ConfigError, load_settings
from openblindysir_server.logging import get, log_event, setup_logging

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
    args = parser.parse_args(argv)
    if args.command == "gen-secrets":
        sys.stdout.write(gen_secrets())
        return 0
    return serve(getattr(args, "host", None), getattr(args, "port", None))
