"""``openblindysir-bridge [run|init|scan|check-ffmpeg]`` (spec §11)."""

import argparse
import asyncio
import contextlib
import getpass
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import warnings
from dataclasses import replace
from pathlib import Path

from openblindysir_bridge import __version__, console, diagnostics, ffmpeg, tempdirs
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.client import BridgeClient, BridgeConnectionRejected
from openblindysir_bridge.config import (
    BridgeConfig,
    load_config,
    persist_bridge_id,
    read_config,
    write_config,
)
from openblindysir_bridge.demo import materialize_demo_library
from openblindysir_bridge.jobs import Faults, JobRunner
from openblindysir_bridge.sandbox import Sandbox
from openblindysir_bridge.scanner import scan
from openblindysir_bridge.sources import scan_sources
from openblindysir_bridge.urls import InvalidServerUrlError, ServerUrl, validate_server_url
from openblindysir_protocol.bridge import JobDone, JobFailed, JobProgress
from openblindysir_protocol.version import PROTOCOL_VERSION

EXIT_USAGE = 2
EXIT_FFMPEG = 3
EXIT_CONNECTION = 4
STATUS_EVERY_S = 30


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openblindysir-bridge",
        description="OpenBlindySir Bridge — vos fichiers restent sur cet appareil.",
        epilog="0 : réussite ; 2 : configuration ; 3 : FFmpeg ; 4 : connexion ; 130 : annulation.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"OpenBlindySir Bridge {__version__} (protocole {PROTOCOL_VERSION})",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "init", "configure", "scan", "check-ffmpeg", "check-config", "doctor"],
    )
    parser.add_argument("--server")
    parser.add_argument("--dir")
    parser.add_argument("--secret", help="discouraged: prefer the environment or config.toml")
    parser.add_argument("--name")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--extensions")
    parser.add_argument(
        "--allow-full-review",
        action="store_true",
        help="allow host-only full audio listening in bounded segments",
    )
    parser.add_argument("--config")
    parser.add_argument(
        "--credentials", help="private TOML issued by the server operator (UUID, name, secret)"
    )
    parser.add_argument(
        "--connect",
        action="store_true",
        help="doctor : scan annoncé et test d'enregistrement (hors partie)",
    )
    parser.add_argument(
        "--json", action="store_true", help="doctor : rapport copiable sans chemins ni secrets"
    )
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--verbose-paths", action="store_true")
    parser.add_argument("--demo-fault", action="append", default=[], help=argparse.SUPPRESS)
    return parser


def purge_tempdirs() -> int:
    """Remove leftovers of previous runs (partial clips of the user's music, spec §11)."""
    return tempdirs.purge(Path(tempfile.gettempdir()))


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


def _say(message: str) -> None:
    print(textwrap.fill(message, width=max(24, min(80, shutil.get_terminal_size().columns))))


def cmd_init(cfg: BridgeConfig) -> int:
    if not sys.stdin.isatty():
        _say(
            "L'assistant requiert un terminal interactif pour masquer le secret. "
            "Utilisez les variables OPENBLINDYSIR_BRIDGE_* en automatisation."
        )
        return EXIT_USAGE
    _say(
        "Configuration du Bridge OpenBlindySir. Les fichiers complets restent ici. "
        "L'écoute intégrale privée reste désactivée sauf accord local."
    )
    server = input(f"URL du serveur [{cfg.server_url or ''}] : ").strip() or cfg.server_url or ""
    folder = input(f"Dossier de musique [{cfg.music_dir or ''}] : ").strip() or str(
        cfg.music_dir or ""
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            secret = getpass.getpass("Secret du Bridge (BRIDGE_SECRET) : ").strip() or (
                cfg.secret or ""
            )
        except getpass.GetPassWarning:
            _say("Saisie masquée indisponible. Ouvrez un terminal interactif puis relancez init.")
            return EXIT_USAGE
    name = input(f"Nom affiché [{cfg.name}] : ").strip() or cfg.name
    updated = replace(cfg, server_url=server, music_dir=Path(folder), secret=secret, name=name)
    try:
        diagnostics.validate_config(updated)
    except (ValueError, OSError, subprocess.SubprocessError):
        _say(
            "Configuration refusée : URL HTTPS sans chemin, dossier accessible sans lien, "
            "nom de 1 à 24 caractères et secret d'au moins 32 caractères requis. "
            + diagnostics.GUIDE
        )
        return EXIT_USAGE
    _say(
        "Résumé : serveur et racine configurés, secret masqué, nom « "
        + name
        + " ». Une configuration existante sera sauvegardée avec des permissions privées."
    )
    if input("Enregistrer ces réglages ? [o/N] : ").strip().lower() not in {"o", "oui", "y", "yes"}:
        _say("Configuration conservée.")
        return 130
    values = read_config(cfg.config_path)
    values.update(
        server_url=server, music_dir=folder, secret=secret, name=name, bridge_id=cfg.bridge_id
    )
    if updated.music_dir != cfg.music_dir:
        values["scanned_folders_json"] = '[""]'
    write_config(
        cfg.config_path,
        values,
        backup=True,
    )
    _say("Réglages enregistrés. Pour les modifier plus tard : openblindysir-bridge init.")
    _say(
        "Le contrôle suivant vérifie FFmpeg, scanne les noms de fichiers puis envoie "
        "le catalogue au serveur. Aucun extrait n'est converti. Le test remplace une "
        "connexion portant le même identifiant : faites-le hors partie."
    )
    if input("Effectuer ces contrôles ? [o/N] : ").strip().lower() not in {"o", "oui", "y", "yes"}:
        _say("Contrôles non effectués. Lancez doctor --connect avant la partie.")
        return 0
    return cmd_doctor(updated, connect=True, as_json=False)


def cmd_doctor(cfg: BridgeConfig, *, connect: bool, as_json: bool) -> int:
    config_ok = True
    try:
        diagnostics.validate_config(cfg)
    except (ValueError, OSError):
        config_ok = False
    info = None
    with contextlib.suppress(ffmpeg.FfmpegMissingError, OSError, subprocess.TimeoutExpired):
        info = ffmpeg.check(ffmpeg.discover(cfg.ffmpeg, cfg.ffprobe), cfg.extensions)
    connection = None
    tracks = None
    if connect and config_ok and info is not None:
        notice = (
            "Scan des noms puis test d'enregistrement ; aucune conversion. "
            "La connexion portant cet identifiant sera remplacée. À utiliser hors partie."
        )
        if as_json:
            print(notice, file=sys.stderr)
        else:
            _say(notice)
        persist_bridge_id(cfg)
        assert cfg.music_dir is not None
        catalog = scan_sources(cfg.music_dir, cfg.scanned_folders, cfg.extensions)
        tracks = len(catalog.entries)
        connection = asyncio.run(diagnostics.check_connection(cfg, info, catalog))
    report = diagnostics.diagnostic_report(
        cfg, config_ok=config_ok, info=info, tracks=tracks, connection=connection
    )
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _say(f"Bridge {__version__} · protocole {PROTOCOL_VERSION}")
        _say("Configuration : " + ("valide" if config_ok else "à corriger avec init"))
        _say("FFmpeg : " + (info.version if info else "à installer ou à réinstaller avec FFprobe"))
        if tracks is not None:
            _say(
                f"Fichiers détectés : {tracks}. Aucun audit de décodage de la bibliothèque entière."
            )
        _say(
            "Connexion : "
            + (
                "enregistrement vérifié (test terminé, connexion fermée)"
                if connection and connection.ok
                else "non vérifiée"
                if connection is None
                else diagnostics.CONNECTION_ACTIONS.get(connection.code, connection.code)
            )
        )
        _say("Pour rester connecté : openblindysir-bridge run. Dépannage : " + diagnostics.GUIDE)
        if connection and connection.protocol_range:
            low, high = connection.protocol_range
            _say(f"Protocole requis : {low}..{high}.")
    if not config_ok:
        return EXIT_USAGE
    if info is None:
        return EXIT_FFMPEG
    return EXIT_CONNECTION if connection is not None and not connection.ok else 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (KeyboardInterrupt, EOFError):
        return 130
    except (ValueError, OSError, subprocess.SubprocessError):
        _say(
            "Configuration ou accès local refusé. Vérifiez le fichier privé, "
            "ses permissions et relancez init. " + diagnostics.GUIDE
        )
        return EXIT_USAGE


def _main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    cfg = load_config(ns, persist_identity=False)
    if ns.command in {"init", "configure"}:
        return cmd_init(cfg)
    if ns.command == "check-config":
        diagnostics.validate_config(cfg)
        _say("Configuration valide ; secrets et chemins exclus du diagnostic.")
        return 0
    if ns.command == "doctor":
        return cmd_doctor(cfg, connect=ns.connect, as_json=ns.json)
    if ns.command == "run" and not ns.demo and not all((cfg.server_url, cfg.music_dir, cfg.secret)):
        code = cmd_init(cfg)
        if code:
            return code
        cfg = load_config(ns, persist_identity=False)
    try:
        tools = ffmpeg.discover(cfg.ffmpeg, cfg.ffprobe)
        info = ffmpeg.check(tools, cfg.extensions)
    except (ffmpeg.FfmpegMissingError, OSError, subprocess.TimeoutExpired) as exc:
        print(
            str(exc) if isinstance(exc, ffmpeg.FfmpegMissingError) else ffmpeg.INSTALL_HINT,
            file=sys.stderr,
        )
        return EXIT_FFMPEG
    if ns.command == "check-ffmpeg":
        print(info.version)
        print(
            "encodeurs : "
            + ", ".join(sorted(e for e in info.encoders if e in {"aac", "libopus", "flac"}))
        )
        return 0
    diagnostics.validate_config(cfg, root=not ns.demo, connection=ns.command != "scan")
    cfg = load_config(ns)
    _say("Scan des noms de fichiers sous la racine autorisée ; aucune conversion globale.")
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
    if cfg.scanned_folders != ("",):
        catalog = scan_sources(music_dir, cfg.scanned_folders, cfg.extensions)
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
    tmpdir = tempdirs.create()
    holder: dict[str, BridgeClient] = {}
    scan_lock = asyncio.Lock()

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
        allow_full_review=cfg.allow_full_review,
    )

    async def rescan(folders: list[str] | None) -> None:
        async with scan_lock:
            current_catalog = state["catalog"]
            assert isinstance(current_catalog, LocalCatalog)
            selected = tuple(folders) if folders is not None else current_catalog.scanned_folders
            try:
                updated = await asyncio.to_thread(scan_sources, music_dir, selected, cfg.extensions)
                values = read_config(cfg.config_path)
                values["scanned_folders_json"] = json.dumps(selected)
                write_config(cfg.config_path, values)
                state["catalog"] = updated
            except (OSError, ValueError):
                state["catalog"] = replace(current_catalog, source_error="inaccessible")
            holder["client"].notify_rescan(force=True)

    client = BridgeClient(
        server=server,
        secret=cfg.secret or "",
        bridge_id=cfg.bridge_id,
        name=cfg.name,
        formats=info.formats(),
        catalog=lambda: state["catalog"],  # type: ignore[arg-type,return-value]
        runner=runner,
        rescan=rescan,
    )
    holder["client"] = client
    tasks = [asyncio.create_task(runner.run()), asyncio.create_task(client.run_forever())]
    folder = (
        "démo synthétique" if ns.demo else str(music_dir) if ns.verbose_paths else "racine privée"
    )
    last_print = -STATUS_EVERY_S
    try:
        while True:
            await asyncio.sleep(0.5)
            if _connection_stopped(tasks[1]):
                return EXIT_CONNECTION
            key = console.read_key()
            if key == "q":
                return 0
            if key == "r":
                client.status.state = "SCANNING"
                await rescan(None)
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
        await _shutdown(tasks, client, tmpdir)


async def _shutdown(tasks: list[asyncio.Task[None]], client: BridgeClient, tmpdir: Path) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    with contextlib.suppress(OSError):
        # The directory was allocated for this process, beneath the named temp root.
        if tmpdir.resolve().parent == Path(tempfile.gettempdir()).resolve():
            shutil.rmtree(tmpdir)
    if client._http is not None:
        await client._http.aclose()


def _connection_stopped(task: asyncio.Task[None]) -> bool:
    if not task.done():
        return False
    try:
        task.result()
    except BridgeConnectionRejected as exc:
        _say(diagnostics.CONNECTION_ACTIONS[exc.code] + ". " + diagnostics.GUIDE)
        if exc.protocol_range:
            _say(f"Protocole requis : {exc.protocol_range[0]}..{exc.protocol_range[1]}.")
    except Exception:
        _say("Connexion interrompue. Lancez doctor. " + diagnostics.GUIDE)
    return True
