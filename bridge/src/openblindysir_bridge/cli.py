"""``openblindysir-bridge [run|init|scan|check-ffmpeg]`` (spec §11)."""

import argparse
import asyncio
import contextlib
import getpass
import shutil
import sys
import tempfile
from pathlib import Path

from openblindysir_bridge import console, ffmpeg
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.client import BridgeClient
from openblindysir_bridge.config import BridgeConfig, load_config, write_config
from openblindysir_bridge.demo import materialize_demo_library
from openblindysir_bridge.jobs import Faults, JobRunner
from openblindysir_bridge.sandbox import Sandbox
from openblindysir_bridge.scanner import scan
from openblindysir_bridge.urls import InvalidServerUrlError, ServerUrl, validate_server_url
from openblindysir_protocol.bridge import JobDone, JobFailed, JobProgress

EXIT_USAGE = 2
EXIT_FFMPEG = 3
STATUS_EVERY_S = 30


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openblindysir-bridge", description="OpenBlindySir Bridge"
    )
    parser.add_argument(
        "command", nargs="?", default="run", choices=["run", "init", "scan", "check-ffmpeg"]
    )
    parser.add_argument("--server")
    parser.add_argument("--dir")
    parser.add_argument("--secret", help="discouraged: prefer the environment or config.toml")
    parser.add_argument("--name")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--extensions")
    parser.add_argument("--config")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--verbose-paths", action="store_true")
    parser.add_argument("--demo-fault", action="append", default=[], help=argparse.SUPPRESS)
    return parser


def purge_tempdirs() -> int:
    """Remove leftovers of previous runs (partial clips of the user's music, spec §11)."""
    failures = 0
    for path in Path(tempfile.gettempdir()).glob(ffmpeg.private_tempdir_prefix() + "*"):
        if ffmpeg.is_own_tempdir(path):
            try:
                shutil.rmtree(path)
            except OSError:
                failures += 1
    return failures


def parse_faults(items: list[str]) -> Faults:
    faults = Faults()
    for item in items:
        key, _, value = item.partition("=")
        if key == "corrupt-upload":
            faults.corrupt_upload = int(value)
        elif key == "delete-track":
            faults.delete_track = int(value)
        elif key == "slow-encode":
            faults.slow_encode_ms = int(value)
    return faults


def cmd_init(cfg: BridgeConfig) -> int:
    print("Configuration du Bridge OpenBlindySir")
    server = input(f"URL du serveur [{cfg.server_url or ''}] : ").strip() or cfg.server_url or ""
    folder = input(f"Dossier de musique [{cfg.music_dir or ''}] : ").strip() or str(
        cfg.music_dir or ""
    )
    secret = getpass.getpass("Secret du Bridge (BRIDGE_SECRET) : ").strip() or (cfg.secret or "")
    name = input(f"Nom affiché [{cfg.name}] : ").strip() or cfg.name
    try:
        validate_server_url(server)
    except InvalidServerUrlError as exc:
        print(f"URL refusée : {exc}", file=sys.stderr)
        return EXIT_USAGE
    write_config(
        cfg.config_path,
        {
            "server_url": server,
            "music_dir": folder,
            "secret": secret,
            "name": name,
            "bridge_id": cfg.bridge_id,
        },
    )
    print(f"Configuration enregistrée : {cfg.config_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    cfg = load_config(ns)
    if ns.command == "init":
        return cmd_init(cfg)
    try:
        tools = ffmpeg.discover(cfg.ffmpeg, cfg.ffprobe)
        info = ffmpeg.check(tools)
    except (ffmpeg.FfmpegMissingError, OSError) as exc:
        print(str(exc) or ffmpeg.INSTALL_HINT, file=sys.stderr)
        return EXIT_FFMPEG
    if ns.command == "check-ffmpeg":
        print(info.version)
        print(
            "encodeurs : "
            + ", ".join(sorted(e for e in info.encoders if e in {"aac", "libopus", "flac"}))
        )
        return 0
    purge_tempdirs()
    if ns.demo:
        music_dir = materialize_demo_library(tools)
    elif cfg.music_dir is not None:
        music_dir = cfg.music_dir
    else:
        print(
            "Aucun dossier : utilisez --dir, OPENBLINDYSIR_BRIDGE_DIR ou `init`.", file=sys.stderr
        )
        return EXIT_USAGE
    if not music_dir.is_dir():
        print("Le dossier de musique est introuvable.", file=sys.stderr)
        return EXIT_USAGE
    result = scan(music_dir, cfg.extensions)
    catalog = LocalCatalog.from_scan(result)
    if ns.command == "scan":
        print(
            f"{console.fr_int(len(catalog.entries))} pistes "
            f"(scan {console.fr_seconds(result.duration_s)}) — "
            f"liens ignorés : {result.skipped_links}, cachés : {result.skipped_hidden}, "
            f"erreurs : {result.skipped_errors}, doublons : {catalog.dropped}"
        )
        return 0
    if not cfg.server_url or not cfg.secret:
        print(
            "URL du serveur et secret requis (--server, variables d'environnement ou init).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        server = validate_server_url(cfg.server_url)
    except InvalidServerUrlError as exc:
        print(f"URL refusée : {exc}", file=sys.stderr)
        return EXIT_USAGE
    if ns.secret:
        print("Attention : le secret passé en argument peut rester dans l'historique du shell.")
    return asyncio.run(
        _run(
            cfg=cfg,
            ns=ns,
            tools=tools,
            info=info,
            server=server,
            music_dir=music_dir,
            catalog=catalog,
            scan_s=result.duration_s,
        )
    )


async def _run(
    *,
    cfg: BridgeConfig,
    ns: argparse.Namespace,
    tools: ffmpeg.FfmpegTools,
    info: ffmpeg.FfmpegInfo,
    server: ServerUrl,
    music_dir: Path,
    catalog: LocalCatalog,
    scan_s: float,
) -> int:
    state = {"catalog": catalog, "scan_s": scan_s}
    tmpdir = Path(tempfile.mkdtemp(prefix=ffmpeg.private_tempdir_prefix()))
    holder: dict[str, BridgeClient] = {}

    async def upload(path: str, token: str, file: Path, sha256: str, mime: str) -> int:
        return await holder["client"].upload(path, token, file, sha256, mime)

    def send(msg: JobProgress | JobDone | JobFailed) -> None:
        holder["client"].send(msg)

    def detail(text: str) -> None:
        if ns.verbose_paths:
            print(text)

    runner = JobRunner(
        tools=tools,
        sandbox=Sandbox(str(music_dir)),
        catalog=lambda: state["catalog"],  # type: ignore[arg-type,return-value]
        uploader=upload,
        send=send,
        tmpdir=tmpdir,
        faults=parse_faults(ns.demo_fault) if ns.demo else Faults(),
        on_detail=detail,
    )
    client = BridgeClient(
        server=server,
        secret=cfg.secret or "",
        bridge_id=cfg.bridge_id,
        name=cfg.name,
        formats=info.formats(),
        catalog=lambda: state["catalog"],  # type: ignore[arg-type,return-value]
        runner=runner,
    )
    holder["client"] = client
    tasks = [asyncio.create_task(runner.run()), asyncio.create_task(client.run_forever())]
    folder = "démo synthétique" if ns.demo else str(music_dir)
    last_print = -STATUS_EVERY_S
    try:
        while True:
            await asyncio.sleep(0.5)
            key = console.read_key()
            if key == "q":
                return 0
            if key == "r":
                client.status.state = "SCANNING"
                result = await asyncio.to_thread(scan, music_dir, cfg.extensions)
                state["catalog"] = LocalCatalog.from_scan(result)
                state["scan_s"] = result.duration_s
                client.notify_rescan()
            loop_time = asyncio.get_running_loop().time()
            if key is not None or loop_time - last_print >= STATUS_EVERY_S:
                last_print = loop_time
                line = console.StatusLine(
                    name=cfg.name,
                    server=server.base(),
                    folder=folder,
                    tracks=len(state["catalog"].entries),  # type: ignore[union-attr]
                    scan_s=float(state["scan_s"]),  # type: ignore[arg-type]
                    state=client.status.state,
                    replaced=client.status.replaced,
                    ok=runner.stats.ok,
                    failed=runner.stats.failed,
                    last_track=runner.stats.last_track,
                    last_seconds=runner.stats.last_seconds,
                )
                print(console.render(line), flush=True)
    finally:
        for task in tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            shutil.rmtree(tmpdir)
        if client._http is not None:
            await client._http.aclose()
