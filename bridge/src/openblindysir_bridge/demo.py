"""``--demo``: a small SYNTHETIC library generated with ``ffmpeg -f lavfi`` (spec §11).

The demo then uses exactly the normal path (scanner, catalogue, sandbox, ffprobe, ffmpeg
template, upload), so every demo run exercises the real pipeline. No protected content.
"""

import subprocess
from pathlib import Path

from openblindysir_bridge.ffmpeg import FfmpegTools
from openblindysir_bridge.tempdirs import create

ARTIST = "OpenBlindySir Demo"
MELODY = "0.4*sin(2*PI*({base}+110*floor(mod(t*4,8)))*t)*lt(mod(t,0.25),0.18)"
CLICKS = "if(lt(mod(t,0.5),0.005),0.9,0)"


def demo_tracks() -> list[tuple[str, str, str]]:
    """(relative path, lavfi expression, title) of the 12 demo tracks."""
    tracks: list[tuple[str, str, str]] = []
    for index, freq in enumerate((220, 330, 440, 550), start=1):
        duration = 60 + 15 * index
        expr = f"sine=frequency={freq}:sample_rate=44100:duration={duration}"
        tracks.append((f"Demo/Sines/sine-{freq}.flac", expr, f"Sinus {freq} Hz"))
    for index, base in enumerate((262, 294, 330, 392), start=1):
        duration = 70 + 20 * index
        expr = f"aevalsrc='{MELODY.format(base=base)}':s=44100:d={duration}"
        tracks.append((f"Demo/Melodies/melodie-{index}.flac", expr, f"Mélodie {index}"))
    for index in range(1, 4):
        duration = 90 + 20 * index
        tracks.append(
            (
                f"Demo/Clicks/clics-{index}.flac",
                f"aevalsrc='{CLICKS}':s=44100:d={duration}",
                f"Clics {index}",
            )
        )
    tracks.append(
        ("Demo/Short/court.flac", "sine=frequency=880:sample_rate=44100:duration=6", "Court")
    )
    return tracks


def materialize_demo_library(tools: FfmpegTools, dest: Path | None = None) -> Path:
    """Generate the demo FLAC files in a private folder and return its path."""
    root = dest or create("demo-")
    for relpath, expr, title in demo_tracks():
        out = root / relpath
        if out.is_file():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(  # noqa: S603 - fixed argv, no shell, synthetic sources only
            [
                tools.ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                expr,
                "-ac",
                "2",
                "-metadata",
                f"title={title}",
                "-metadata",
                f"artist={ARTIST}",
                "-c:a",
                "flac",
                "-y",
                str(out),
            ],
            check=True,
            timeout=60,
        )
    return root
