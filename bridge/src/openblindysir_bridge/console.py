"""Console status (spec §11): French texts, no file names unless ``--verbose-paths``."""

import sys
from dataclasses import dataclass

from openblindysir_bridge import __version__

STATES = {
    "SCANNING": "SCAN EN COURS",
    "CONNECTING": "CONNEXION…",
    "BACKOFF": "NOUVEL ESSAI",
    "ONLINE": "CONNECTÉ",
}


def fr_int(value: int) -> str:
    return f"{value:,}".replace(",", "\u202f")


def fr_seconds(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " s"


@dataclass
class StatusLine:
    name: str
    server: str
    folder: str
    tracks: int
    scan_s: float
    state: str
    replaced: bool
    ok: int
    failed: int
    last_track: str | None
    last_seconds: float | None


def render(status: StatusLine) -> str:
    state = STATES.get(status.state, status.state)
    if status.replaced:
        state = "Remplacé par un autre Bridge"
    last = ""
    if status.last_track:
        took = f" {fr_seconds(status.last_seconds)}" if status.last_seconds is not None else ""
        last = f" · dernier {status.last_track[:8]}…{took}"
    plural = "échecs" if status.failed > 1 else "échec"
    return "\n".join(
        [
            f"OpenBlindySir Bridge {__version__} — « {status.name} »",
            f"Serveur : {status.server}   {state}",
            f"Dossier : {status.folder} — {fr_int(status.tracks)} pistes "
            f"(scan {fr_seconds(status.scan_s)})",
            f"Jobs    : {status.ok} OK · {status.failed} {plural}{last}",
            "[r] rescanner   [q] quitter" if sys.stdin.isatty() else "",
        ]
    ).rstrip()


def read_key() -> str | None:
    """Non-blocking key read (``r`` / ``q``); None when no key or not a terminal."""
    if not sys.stdin.isatty():
        return None
    if sys.platform == "win32":
        import msvcrt  # noqa: PLC0415

        if msvcrt.kbhit():
            return msvcrt.getwch().lower()
        return None
    import select  # noqa: PLC0415

    ready, _, _ = select.select([sys.stdin], [], [], 0)
    return sys.stdin.read(1).lower() if ready else None
