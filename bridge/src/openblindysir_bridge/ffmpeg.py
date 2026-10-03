"""FFmpeg/ffprobe: discovery and the FIXED command templates (spec §10).

Arguments are lists, never a shell. The only variables are the resolved path (from the
catalogue), start and duration (bounded by the Bridge) and the format (fixed list).
``-protocol_whitelist file`` and ``-format_whitelist`` (closed list of audio demuxers) keep
FFmpeg from following playlists such as ffconcat out of the root (spike S1 finding).
"""

import asyncio
import contextlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from openblindysir_protocol.enums import ClipFormat
from openblindysir_protocol.media import DEMUXER_WHITELIST, INPUT_DEMUXER_BY_EXTENSION

PROBE_TIMEOUT_S = 10.0
ENCODE_TIMEOUT_S = 30.0
STDERR_LIMIT = 8192
STDOUT_LIMIT = 128 * 1024
TAG_MAX = 200
MIN_VERSION = (4, 4)
INSTALL_HINT = (
    "FFmpeg est introuvable. Installez-le : winget install Gyan.FFmpeg (Windows), "
    "brew install ffmpeg (macOS) ou sudo apt install ffmpeg (Linux), "
    "ou indiquez son chemin avec --ffmpeg."
)
CREATE_NO_WINDOW = 0x08000000


class FfmpegMissingError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class FfmpegTools:
    ffmpeg: str
    ffprobe: str


@dataclass(frozen=True, slots=True)
class FfmpegInfo:
    version: str
    encoders: frozenset[str]
    demuxers: frozenset[str] = frozenset()
    muxers: frozenset[str] = frozenset()
    filters: frozenset[str] = frozenset()

    def formats(self) -> list[ClipFormat]:
        found = []
        if "aac" in self.encoders:
            found.append(ClipFormat.AAC)
        if "libopus" in self.encoders and (not self.muxers or "webm" in self.muxers):
            found.append(ClipFormat.OPUS)
        return found


@dataclass(frozen=True, slots=True)
class CompletedRun:
    returncode: int | None  # None: killed after a timeout
    stdout: bytes
    stderr: str  # truncated; may contain the absolute path: console only with --verbose-paths


@dataclass(frozen=True, slots=True)
class ProbeResult:
    duration_s: float
    has_audio: bool
    title: str | None
    artist: str | None


def discover(ffmpeg: str | None = None, ffprobe: str | None = None) -> FfmpegTools:
    ffmpeg_path = shutil.which(ffmpeg or "ffmpeg") or ffmpeg
    if not ffmpeg_path or not Path(ffmpeg_path).is_file():
        raise FfmpegMissingError(INSTALL_HINT)
    if ffprobe is None:
        name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
        sibling = Path(ffmpeg_path).with_name(name)
        ffprobe = str(sibling) if sibling.is_file() else shutil.which("ffprobe")
    ffprobe = shutil.which(ffprobe) or ffprobe if ffprobe else None
    if not ffprobe or not Path(ffprobe).is_file():
        raise FfmpegMissingError(INSTALL_HINT)
    return FfmpegTools(ffmpeg=str(ffmpeg_path), ffprobe=str(ffprobe))


def _creationflags() -> int:
    return CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _capabilities(tool: str, option: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed options, executable selected locally
        [tool, "-hide_banner", option],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=10,
        check=False,
        creationflags=_creationflags(),
    )
    if result.returncode or len(result.stdout) > STDOUT_LIMIT:
        raise FfmpegMissingError("Vérification FFmpeg impossible. Réinstallez FFmpeg et ffprobe.")
    return result.stdout


def _names(output: str, flag: str) -> frozenset[str]:
    return frozenset(
        name
        for line in output.splitlines()
        if len(parts := line.split()) >= 2 and parts[0].startswith(flag)
        for name in parts[1].split(",")
    )


def check(tools: FfmpegTools, extensions: frozenset[str] | None = None) -> FfmpegInfo:
    """Check both tools, fixed demuxers, AAC muxing and normalization filters."""
    version = ""
    for label, executable in (("FFmpeg", tools.ffmpeg), ("ffprobe", tools.ffprobe)):
        output = _capabilities(executable, "-version")
        match = re.search(r"version\s+n?(\d+)\.(\d+)(?:\.(\d+))?", output)
        if match and (int(match[1]), int(match[2])) < MIN_VERSION:
            raise FfmpegMissingError(f"{label} trop ancien ; version 4.4 ou plus requise.")
        if label == "FFmpeg":
            version = (
                f"FFmpeg {match[0].removeprefix('version ')}"
                if match
                else "FFmpeg (build personnalisé)"
            )
    encoders = _names(_capabilities(tools.ffmpeg, "-encoders"), "A")
    demuxers = _names(_capabilities(tools.ffmpeg, "-demuxers"), "D")
    probe_demuxers = _names(_capabilities(tools.ffprobe, "-demuxers"), "D")
    muxers = _names(_capabilities(tools.ffmpeg, "-muxers"), "E")
    filter_output = _capabilities(tools.ffmpeg, "-filters")
    filters = frozenset(
        parts[1]
        for line in filter_output.splitlines()
        if len(parts := line.split()) >= 3 and "->" in parts[2]
    )
    required = {INPUT_DEMUXER_BY_EXTENSION[e] for e in (extensions or INPUT_DEMUXER_BY_EXTENSION)}
    missing = sorted(required - (demuxers & probe_demuxers))
    if missing:
        raise FfmpegMissingError(
            "Démultiplexeurs absents : " + ", ".join(missing) + ". Réinstallez FFmpeg complet."
        )
    if "aac" not in encoders or "ipod" not in muxers:
        raise FfmpegMissingError("Encodeur AAC ou sortie M4A absents. Réinstallez FFmpeg complet.")
    if not {"loudnorm", "afade", "silencedetect"} <= filters:
        raise FfmpegMissingError("Filtres audio absents. Réinstallez FFmpeg complet.")
    return FfmpegInfo(version, encoders, demuxers, muxers, filters)


def _input_options(real_path: str) -> list[str]:
    """Force the whitelisted container; MOV references stay disabled explicitly."""
    demuxer = INPUT_DEMUXER_BY_EXTENSION[Path(real_path).suffix.lower()]
    options = ["-protocol_whitelist", "file", "-format_whitelist", DEMUXER_WHITELIST, "-f", demuxer]
    if demuxer == "mov":
        options += ["-enable_drefs", "0", "-use_absolute_path", "0"]
    return options


def probe_argv(tools: FfmpegTools, real_path: str) -> list[str]:
    return [
        tools.ffprobe,
        "-v", "error",
        *_input_options(real_path),
        "-select_streams", "a:0",
        "-show_entries",
        "format=duration:format_tags=title,artist:stream=codec_type,duration:stream_tags=title,artist",
        "-of", "json",
        "file:" + real_path,
    ]  # fmt: skip


def duration_argv(tools: FfmpegTools, clip_path: str) -> list[str]:
    """Measure the clip actually produced (output check of spec §10)."""
    return [
        tools.ffprobe,
        "-v", "error",
        "-protocol_whitelist", "file",
        "-show_entries", "format=duration",
        "-of", "json",
        "file:" + clip_path,
    ]  # fmt: skip


def encode_argv(
    tools: FfmpegTools,
    real_path: str,
    out_path: str,
    *,
    start: float,
    duration: float,
    bitrate_kbps: int,
    clip_format: ClipFormat,
    normalize_audio: bool = True,
    fade_audio: bool = True,
) -> list[str]:
    """The fixed §10 template: ``-ss`` before ``-i``, ``-t`` after, no metadata nor cover."""
    fade_out = max(0.0, duration - 1.5)
    filters = "loudnorm=I=-16:TP=-1.5:LRA=11," if normalize_audio else ""
    filters += (
        f"afade=t=in:st=0:d=0.3,afade=t=out:st={fade_out:.3f}:d=1.5" if fade_audio else "anull"
    )
    argv = [
        tools.ffmpeg,
        "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "1",
        *_input_options(real_path),
        "-ss", f"{start:.3f}",
        "-i", "file:" + real_path,
        "-t", f"{duration:.3f}",
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-ac", "2", "-ar", "48000",
        "-af", filters,
    ]  # fmt: skip
    if clip_format is ClipFormat.OPUS:
        argv += ["-c:a", "libopus", "-b:a", f"{bitrate_kbps}k", "-f", "webm"]
    else:
        argv += ["-c:a", "aac", "-b:a", f"{bitrate_kbps}k", "-movflags", "+faststart", "-f", "mp4"]
    argv += ["-y", "file:" + out_path]
    return argv


def analysis_argv(tools: FfmpegTools, real_path: str, start: float, duration: float) -> list[str]:
    return [
        tools.ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "info",
        "-threads",
        "1",
        *_input_options(real_path),
        "-ss",
        f"{start:.3f}",
        "-i",
        "file:" + real_path,
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-af",
        "silencedetect=n=-45dB:d=0.4,volumedetect",
        "-f",
        "null",
        "-",
    ]


def analyze_silence(stderr: str, duration: float | None = None) -> tuple[bool, float]:
    maximum = re.search(r"max_volume:\s*(-?inf|[-\d.]+)\s*dB", stderr)
    # Quiet recordings can be made audible by loudnorm; reject only near-zero signals.
    silent = maximum is None or float(maximum.group(1)) <= -80
    start = re.search(r"silence_start:\s*([-\d.]+)", stderr)
    end = re.search(r"silence_end:\s*([-\d.]+)", stderr)
    leading = float(end.group(1)) if start and end and float(start.group(1)) < 0.1 else 0.0
    if duration is not None and leading >= duration - 0.1:
        leading = 0.0
    return silent, leading


async def run_bounded(argv: list[str], timeout_s: float) -> CompletedRun:
    """Run without a shell; kill on timeout or cancellation."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=_creationflags(),
    )

    async def drain(stream: asyncio.StreamReader | None, limit: int, *, stop: bool) -> bytes:
        result = bytearray()
        assert stream is not None
        while chunk := await stream.read(65536):
            remaining = max(0, limit - len(result))
            if stop:
                result.extend(chunk[:remaining])
            else:
                result.extend(chunk)
                del result[:-limit]
            if stop and len(chunk) > remaining:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
        return bytes(result)

    output = asyncio.gather(
        drain(process.stdout, STDOUT_LIMIT, stop=True),
        drain(process.stderr, STDERR_LIMIT, stop=False),
    )
    try:
        stdout, stderr = await asyncio.wait_for(asyncio.shield(output), timeout=timeout_s)
        await process.wait()
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        await output
        return CompletedRun(None, b"", "timeout")
    except asyncio.CancelledError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        await output
        raise
    text = stderr.decode("utf-8", errors="replace")[-STDERR_LIMIT:]
    return CompletedRun(process.returncode, stdout, text)


def _clean_tag(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFC", value)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in {"Cc", "Cf"}).strip()
    return text[:TAG_MAX] or None


def _tag(tags: object, name: str) -> str | None:
    if not isinstance(tags, dict):
        return None
    for key, value in tags.items():
        if isinstance(key, str) and key.lower() == name:
            return _clean_tag(value)
    return None


def parse_probe(stdout: bytes) -> ProbeResult | None:
    try:
        data = json.loads(stdout.decode("utf-8", errors="replace"))
        duration = float(data["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None
    streams = data.get("streams") or []
    has_audio = any(s.get("codec_type") == "audio" for s in streams if isinstance(s, dict))
    first_audio = next(
        (s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"), None
    )
    if first_audio is not None:
        with contextlib.suppress(KeyError, ValueError, TypeError):
            duration = min(duration, float(first_audio["duration"]))
    if not math.isfinite(duration) or duration <= 0 or duration > 86400:
        return None
    fmt_tags = data.get("format", {}).get("tags")
    title = _tag(fmt_tags, "title")
    artist = _tag(fmt_tags, "artist")
    for s in streams:
        if isinstance(s, dict) and s.get("codec_type") == "audio":
            title = title or _tag(s.get("tags"), "title")
            artist = artist or _tag(s.get("tags"), "artist")
            break
    return ProbeResult(duration_s=duration, has_audio=has_audio, title=title, artist=artist)


def parse_duration(stdout: bytes) -> float | None:
    try:
        return float(json.loads(stdout.decode("utf-8", errors="replace"))["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None


def private_tempdir_prefix() -> str:
    return "openblindysir-bridge-"


def is_own_tempdir(path: Path) -> bool:
    if not path.is_dir() or not path.name.startswith(private_tempdir_prefix()):
        return False
    if hasattr(os, "getuid"):
        return path.stat().st_uid == getattr(os, "getuid")()  # noqa: B009 - POSIX only
    return True
