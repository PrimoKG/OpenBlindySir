"""FFmpeg/ffprobe: discovery and the FIXED command templates (spec §10).

Arguments are lists, never a shell. The only variables are the resolved path (from the
catalogue), start and duration (bounded by the Bridge) and the format (fixed list).
``-protocol_whitelist file`` and ``-format_whitelist`` (closed list of audio demuxers) keep
FFmpeg from following playlists such as ffconcat out of the root (spike S1 finding).
"""

import asyncio
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from openblindysir_protocol.enums import ClipFormat

DEMUXER_WHITELIST = "mp3,flac,wav,mov,ogg,aiff,asf,aac"
PROBE_TIMEOUT_S = 10.0
ENCODE_TIMEOUT_S = 30.0
STDERR_LIMIT = 2048
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

    def formats(self) -> list[ClipFormat]:
        found = []
        if "aac" in self.encoders:
            found.append(ClipFormat.AAC)
        if "libopus" in self.encoders:
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
    ffmpeg_path = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg_path or not Path(ffmpeg_path).is_file():
        raise FfmpegMissingError(INSTALL_HINT)
    if ffprobe is None:
        name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
        sibling = Path(ffmpeg_path).with_name(name)
        ffprobe = str(sibling) if sibling.is_file() else shutil.which("ffprobe")
    if not ffprobe or not Path(ffprobe).is_file():
        raise FfmpegMissingError(INSTALL_HINT)
    return FfmpegTools(ffmpeg=str(ffmpeg_path), ffprobe=str(ffprobe))


def _creationflags() -> int:
    return CREATE_NO_WINDOW if sys.platform == "win32" else 0


def check(tools: FfmpegTools) -> FfmpegInfo:
    """Version (>= 4.4) and available encoders."""
    flags = _creationflags()
    version_out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [tools.ffmpeg, "-hide_banner", "-version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        creationflags=flags,
    ).stdout
    first = version_out.splitlines()[0] if version_out else ""
    match = re.search(r"version\s+n?(\d+)\.(\d+)", first)
    if match and (int(match.group(1)), int(match.group(2))) < MIN_VERSION:
        raise FfmpegMissingError(f"FFmpeg trop ancien ({first}) ; version 4.4 ou plus requise.")
    encoders_out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [tools.ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        creationflags=flags,
    ).stdout
    encoders = {
        parts[1]
        for line in encoders_out.splitlines()
        if (parts := line.split()) and len(parts) >= 2 and parts[0].startswith("A")
    }
    return FfmpegInfo(version=first, encoders=frozenset(encoders))


def probe_argv(tools: FfmpegTools, real_path: str) -> list[str]:
    return [
        tools.ffprobe,
        "-v", "error",
        "-protocol_whitelist", "file",
        "-format_whitelist", DEMUXER_WHITELIST,
        "-show_entries",
        "format=duration:format_tags=title,artist:stream=codec_type:stream_tags=title,artist",
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
) -> list[str]:
    """The fixed §10 template: ``-ss`` before ``-i``, ``-t`` after, no metadata nor cover."""
    fade_out = max(0.0, duration - 1.5)
    argv = [
        tools.ffmpeg,
        "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "1",
        "-protocol_whitelist", "file",
        "-format_whitelist", DEMUXER_WHITELIST,
        "-ss", f"{start:.3f}",
        "-i", "file:" + real_path,
        "-t", f"{duration:.3f}",
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-ac", "2", "-ar", "48000",
        "-af", f"afade=t=in:st=0:d=0.3,afade=t=out:st={fade_out:.3f}:d=1.5",
    ]  # fmt: skip
    if clip_format is ClipFormat.OPUS:
        argv += ["-c:a", "libopus", "-b:a", f"{bitrate_kbps}k", "-f", "webm"]
    else:
        argv += ["-c:a", "aac", "-b:a", f"{bitrate_kbps}k", "-movflags", "+faststart", "-f", "mp4"]
    argv += ["-y", "file:" + out_path]
    return argv


async def run_bounded(argv: list[str], timeout_s: float) -> CompletedRun:
    """Run without a shell; kill on timeout or cancellation."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=_creationflags(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        return CompletedRun(None, b"", "timeout")
    except asyncio.CancelledError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        raise
    text = stderr.decode("utf-8", errors="replace")[:STDERR_LIMIT]
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
    fmt_tags = data.get("format", {}).get("tags")
    title = _tag(fmt_tags, "title")
    artist = _tag(fmt_tags, "artist")
    for s in streams:
        if isinstance(s, dict) and s.get("codec_type") == "audio":
            title = title or _tag(s.get("tags"), "title")
            artist = artist or _tag(s.get("tags"), "artist")
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
