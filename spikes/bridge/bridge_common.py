"""Shared helpers for the S1 Bridge spike (throwaway code, standard library only).

Imported by the spike scripts that sit next to this file (``uv run <script>.py`` puts the
script directory on ``sys.path``). Implements, as literally as possible:

- spec §11 / docs/bridge-security.md: iterative ``os.scandir`` scan, explicit refusal of
  symlinks and junctions, hidden/system files skipped, extension whitelist, POSIX NFC
  relpaths, ``track_id = "t_" + sha256(relpath)[:16]``, catalog hash, open-time sandbox
  check (realpath again + commonpath confinement + regular file + size/mtime);
- spec §10: ffprobe call, start point rule and the exact FFmpeg template.

Nothing here ever prints a file name: callers decide (``--verbose-paths``).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

IS_WINDOWS = os.name == "nt"

AUDIO_EXTS: frozenset[str] = frozenset(
    {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".aiff", ".wma"}
)

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# Timeouts from spec §11.
FFPROBE_TIMEOUT_S = 10.0
FFMPEG_TIMEOUT_S = 30.0
UPLOAD_TIMEOUT_S = 60.0

# Clip bounds enforced by the Bridge itself (spec §8.3: the Bridge caps what the server asks).
CLIP_MIN_S = 5.0
CLIP_MAX_S = 30.0
TOO_SHORT_S = 8.0
FADE_IN_S = 0.3
FADE_OUT_S = 1.5
SHORT_CLIP_TOLERANCE_S = 0.25  # output check: shorter than planned by more -> re-encode

# Fixed list of output formats (spec §10: "une valeur parmi une liste fixe").
OUTPUT_FORMATS: dict[str, dict] = {
    "aac": {
        "suffix": ".m4a",
        "codec_args": ["-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"],
        "codec_name": "aac",
        "content_type": "audio/mp4",
    },
    "opus": {
        "suffix": ".ogg",
        "codec_args": ["-c:a", "libopus", "-b:a", "96k"],
        "codec_name": "opus",
        "content_type": "audio/ogg",
    },
}

TEMP_PREFIX = "openblindysir-bridge-"

# Normalized failure codes (spec §7.3). INVALID_OUTPUT is spike-only (bench verification).
NOT_FOUND = "NOT_FOUND"
DECODE_ERROR = "DECODE_ERROR"
TOO_SHORT = "TOO_SHORT"
TIMEOUT = "TIMEOUT"
INVALID_OUTPUT = "INVALID_OUTPUT"


class JobError(Exception):
    """A failure carrying a normalized code and an internal reason (never a path)."""

    def __init__(self, code: str, reason: str = "", detail: str = "") -> None:
        super().__init__(f"{code}: {reason}" if reason else code)
        self.code = code
        self.reason = reason
        self.detail = detail  # tool stderr: MAY contain paths, print only with --verbose-paths


def setup_console() -> None:
    """Make stdout/stderr UTF-8 with replacement, so a piped Windows console never crashes."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


# --------------------------------------------------------------------------------------------
# Tools lookup
# --------------------------------------------------------------------------------------------


def find_tool(name: str, cli_value: str | None, env_var: str, sibling_of: str | None = None) -> str:
    """CLI option > environment variable > next to the other tool > PATH."""
    for candidate in (cli_value, os.environ.get(env_var)):
        if candidate:
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
            raise SystemExit(f"{name}: not found at the given location (option or {env_var})")
    if sibling_of:
        exe = name + (".exe" if IS_WINDOWS else "")
        candidate = os.path.join(os.path.dirname(sibling_of), exe)
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which(name)
    if found:
        return found
    raise SystemExit(
        f"{name} not found. Pass --{name} PATH or set {env_var}, or install FFmpeg "
        "(winget install Gyan.FFmpeg | brew install ffmpeg | apt install ffmpeg)."
    )


def find_ffmpeg_pair(ffmpeg_opt: str | None, ffprobe_opt: str | None) -> tuple[str, str]:
    ffmpeg = find_tool("ffmpeg", ffmpeg_opt, "OPENBLINDYSIR_FFMPEG")
    ffprobe = find_tool("ffprobe", ffprobe_opt, "OPENBLINDYSIR_FFPROBE", sibling_of=ffmpeg)
    return ffmpeg, ffprobe


def ffmpeg_info(ffmpeg: str) -> tuple[str, set[str]]:
    """Return (first version line, available encoders among aac/libopus)."""
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True, timeout=10,
        stdin=subprocess.DEVNULL,
    ).stdout
    version = out.splitlines()[0] if out else "unknown"
    enc = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10,
        stdin=subprocess.DEVNULL,
    ).stdout
    present = {name for name in ("aac", "libopus") if f" {name} " in enc}
    return version, present


# --------------------------------------------------------------------------------------------
# Scan and catalog
# --------------------------------------------------------------------------------------------


def make_track_id(relpath: str) -> str:
    return "t_" + hashlib.sha256(relpath.encode("utf-8")).hexdigest()[:16]


@dataclass
class Track:
    track_id: str
    relpath: str  # POSIX, NFC: what the server sees
    folder: str
    ext: str
    size: int
    mtime_ns: int
    fs_relpath: str  # real on-disk relative path (OS separators, original normalization): private

    def public(self) -> dict:
        return {
            "track_id": self.track_id,
            "relpath": self.relpath,
            "folder": self.folder,
            "ext": self.ext,
            "size": self.size,
        }


@dataclass
class ScanStats:
    dirs: int = 0
    files_seen: int = 0
    accepted: int = 0
    total_bytes: int = 0
    symlinks_skipped: int = 0
    junctions_skipped: int = 0
    dotfiles_skipped: int = 0
    hidden_attr_skipped: int = 0
    system_attr_skipped: int = 0
    ext_skipped: int = 0
    other_type_skipped: int = 0
    outside_root_refused: int = 0
    errors: int = 0
    nfc_normalized: int = 0
    nfc_collisions: int = 0
    reparse_other: int = 0
    empty_files: int = 0
    elapsed_s: float = 0.0
    realpath_s: float = 0.0
    ext_hist: Counter = field(default_factory=Counter)


def is_within(real: str, root_real: str) -> bool:
    try:
        common = os.path.commonpath([real, root_real])
    except ValueError:  # different drives on Windows, or mixed absolute/relative
        return False
    return os.path.normcase(common) == os.path.normcase(root_real)


def resolve_root(root: str) -> str:
    root_real = os.path.realpath(os.path.abspath(root), strict=True)
    if not os.path.isdir(root_real):
        raise SystemExit("root is not a directory")
    return root_real


def scan_library(
    root: str, *, exts: frozenset[str] = AUDIO_EXTS, check_realpath: bool = True
) -> tuple[str, dict[str, Track], ScanStats]:
    """Iterative scan of one root. Returns (root_real, {track_id: Track}, stats)."""
    t0 = time.perf_counter()
    root_real = resolve_root(root)
    stats = ScanStats()
    tracks: dict[str, Track] = {}
    stack = [root_real]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            stats.errors += 1
            continue
        for entry in entries:
            try:
                # Explicit link tests first: os.walk follows junctions on Windows.
                if entry.is_symlink():
                    stats.symlinks_skipped += 1
                    continue
                if os.path.isjunction(entry.path):
                    stats.junctions_skipped += 1
                    continue
                st = entry.stat(follow_symlinks=False)
                if entry.name.startswith("."):
                    stats.dotfiles_skipped += 1
                    continue
                attrs = getattr(st, "st_file_attributes", 0)
                if attrs & FILE_ATTRIBUTE_HIDDEN:
                    stats.hidden_attr_skipped += 1
                    continue
                if attrs & FILE_ATTRIBUTE_SYSTEM:
                    stats.system_attr_skipped += 1
                    continue
                if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
                    # Neither symlink nor junction (e.g. OneDrive placeholder, dedup): counted,
                    # kept; the realpath confinement below still applies.
                    stats.reparse_other += 1
                if entry.is_dir(follow_symlinks=False):
                    stats.dirs += 1
                    stack.append(entry.path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    stats.other_type_skipped += 1
                    continue
                stats.files_seen += 1
                ext = os.path.splitext(entry.name)[1].lower()
                if ext not in exts:
                    stats.ext_skipped += 1
                    continue
                if check_realpath:
                    tr = time.perf_counter()
                    real = os.path.realpath(entry.path)
                    stats.realpath_s += time.perf_counter() - tr
                    if not is_within(real, root_real):
                        stats.outside_root_refused += 1
                        continue
                fs_rel = os.path.relpath(entry.path, root_real)
                posix = fs_rel.replace(os.sep, "/")
                rel = unicodedata.normalize("NFC", posix)
                if rel != posix:
                    stats.nfc_normalized += 1
                track_id = make_track_id(rel)
                if track_id in tracks:
                    # Two on-disk names normalize to the same NFC relpath: first one wins.
                    stats.nfc_collisions += 1
                    continue
                folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
                tracks[track_id] = Track(
                    track_id=track_id, relpath=rel, folder=folder, ext=ext.lstrip("."),
                    size=st.st_size, mtime_ns=st.st_mtime_ns, fs_relpath=fs_rel,
                )
                stats.accepted += 1
                stats.total_bytes += st.st_size
                stats.ext_hist[ext] += 1
                if st.st_size == 0:
                    stats.empty_files += 1
            except OSError:
                stats.errors += 1
    stats.elapsed_s = time.perf_counter() - t0
    return root_real, tracks, stats


def catalog_entries(tracks: dict[str, Track]) -> list[dict]:
    return [t.public() for t in sorted(tracks.values(), key=lambda t: t.relpath)]


def catalog_hash(entries: list[dict]) -> str:
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def catalog_payload(tracks: dict[str, Track]) -> tuple[bytes, bytes, str]:
    """Return (raw JSON bytes, gzip bytes, catalog_hash)."""
    entries = catalog_entries(tracks)
    chash = catalog_hash(entries)
    raw = json.dumps(
        {"catalog_hash": chash, "entries": entries}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return raw, gzip.compress(raw, compresslevel=6, mtime=0), chash


def save_private_catalog(path: str, root_real: str, tracks: dict[str, Track]) -> None:
    """Local-only file (contains real paths): feeds ffmpeg_bench.py. Never share it."""
    data = {
        "root_real": root_real,
        "tracks": [t.__dict__ for t in sorted(tracks.values(), key=lambda t: t.relpath)],
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=0)


def load_private_catalog(path: str) -> tuple[str, dict[str, Track]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    tracks = {t["track_id"]: Track(**t) for t in data["tracks"]}
    return data["root_real"], tracks


# --------------------------------------------------------------------------------------------
# Open-time sandbox check
# --------------------------------------------------------------------------------------------


def resolve_for_open(root_real: str, tracks: dict[str, Track], track_id: object) -> str:
    """track_id is a dictionary key, never a path. Returns the resolved absolute path."""
    if not isinstance(track_id, str):
        raise JobError(NOT_FOUND, "track_id not a string")
    track = tracks.get(track_id)
    if track is None:
        raise JobError(NOT_FOUND, "unknown track_id")
    candidate = os.path.join(root_real, track.fs_relpath)
    try:
        real = os.path.realpath(candidate, strict=True)
    except OSError:
        raise JobError(NOT_FOUND, "file missing") from None
    if not is_within(real, root_real):
        raise JobError(NOT_FOUND, "resolves outside root")
    try:
        st = os.stat(real, follow_symlinks=False)
    except OSError:
        raise JobError(NOT_FOUND, "stat failed") from None
    if not stat.S_ISREG(st.st_mode):
        raise JobError(NOT_FOUND, "not a regular file")
    if st.st_size != track.size or st.st_mtime_ns != track.mtime_ns:
        raise JobError(NOT_FOUND, "changed since scan (size/mtime)")
    return real


# --------------------------------------------------------------------------------------------
# ffprobe / start point / ffmpeg template
# --------------------------------------------------------------------------------------------


def ffprobe_argv(ffprobe: str, real_path: str) -> list[str]:
    return [
        ffprobe, "-v", "warning", "-hide_banner", "-protocol_whitelist", "file",
        "-show_entries",
        "format=duration,format_name:format_tags:stream=index,codec_type,codec_name,"
        "sample_rate,channels:stream_tags:stream_disposition=attached_pic",
        "-of", "json", "file:" + real_path,
    ]  # fmt: skip


@dataclass
class ProbeInfo:
    duration: float | None
    format_name: str
    audio: list[dict]
    video: list[dict]
    other_streams: int
    format_tags: dict[str, str]
    stream_tags: dict[str, str]
    duration_estimated: bool = False  # ffprobe guessed it from the bitrate (unreliable)
    duration_probed: float | None = None  # what ffprobe said, when replaced by a measure

    def tag(self, key: str) -> str | None:
        return self.format_tags.get(key) or self.stream_tags.get(key)


def parse_probe(stdout: str) -> ProbeInfo:
    data = json.loads(stdout or "{}")
    fmt = data.get("format", {}) or {}
    streams = data.get("streams", []) or []
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    video = [s for s in streams if s.get("codec_type") == "video"]
    duration = None
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        pass
    ftags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    stags = {k.lower(): v for k, v in ((audio[0].get("tags") if audio else None) or {}).items()}
    return ProbeInfo(
        duration=duration, format_name=fmt.get("format_name", ""), audio=audio, video=video,
        other_streams=len(streams) - len(audio) - len(video), format_tags=ftags, stream_tags=stags,
    )


def run_tool(argv: list[str], timeout: float) -> subprocess.CompletedProcess:
    """Run a tool as an argument list (never a shell). The child is killed on timeout."""
    try:
        return subprocess.run(
            argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise JobError(TIMEOUT, f"{os.path.basename(argv[0])} timeout") from None


ESTIMATED_DURATION_MARK = "Estimating duration from bitrate"


def probe(ffprobe: str, real_path: str, extra_args: list[str] | None = None) -> ProbeInfo:
    argv = ffprobe_argv(ffprobe, real_path)
    if extra_args:
        argv[1:1] = extra_args
    proc = run_tool(argv, FFPROBE_TIMEOUT_S)
    stderr = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise JobError(DECODE_ERROR, "ffprobe failed", stderr)
    try:
        info = parse_probe(proc.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        raise JobError(DECODE_ERROR, "ffprobe output unreadable") from None
    info.duration_estimated = ESTIMATED_DURATION_MARK in stderr
    if not info.audio:
        raise JobError(DECODE_ERROR, "no audio stream")
    if info.duration is None or not math.isfinite(info.duration) or info.duration <= 0:
        raise JobError(DECODE_ERROR, "no duration")
    return info


def measure_duration(ffmpeg: str, real_path: str, extra_args: list[str] | None = None) -> float:
    """Real duration by demuxing the whole first audio stream without decoding (-c copy).
    Used only when ffprobe estimated the duration from the bitrate (VBR MP3 without
    Xing/VBRI header, ADTS AAC): ~70 ms for a 1 MB MP3 on the dev machine."""
    argv = [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", *(extra_args or []),
            "-protocol_whitelist", "file", "-i", "file:" + real_path,
            "-map", "0:a:0", "-c", "copy", "-f", "null", "-progress", "pipe:1", "-nostats", "-"]
    proc = run_tool(argv, FFPROBE_TIMEOUT_S)
    values = [line.split("=", 1)[1] for line in proc.stdout.decode("ascii", "replace").splitlines()
              if line.startswith("out_time_us=")]
    try:
        seconds = int(values[-1]) / 1e6
    except (IndexError, ValueError):
        raise JobError(DECODE_ERROR, "duration measure failed",
                       proc.stderr.decode("utf-8", "replace")) from None
    if proc.returncode != 0 or seconds <= 0:
        raise JobError(DECODE_ERROR, "duration measure failed", proc.stderr.decode("utf-8", "replace"))
    return seconds


def clamp_request(start_fraction: object, duration: object) -> tuple[float, float]:
    """The Bridge caps what the server asks (spec §8.3 / §11)."""
    try:
        frac = float(start_fraction)  # type: ignore[arg-type]
        clip = float(duration)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):  # float(10**400) raises OverflowError
        frac, clip = 0.5, CLIP_MAX_S
    if not math.isfinite(frac):
        frac = 0.5
    if not math.isfinite(clip):
        clip = CLIP_MAX_S
    frac = min(max(frac, 0.0), 0.999999)
    clip = min(max(clip, CLIP_MIN_S), CLIP_MAX_S)
    return frac, clip


def compute_start(track_duration: float, clip: float, start_fraction: float) -> tuple[float, float, str]:
    """Spec §10 start point rule. Returns (start, clip_duration, rule)."""
    if track_duration < TOO_SHORT_S:
        raise JobError(TOO_SHORT, "track shorter than 8 s")
    if track_duration <= clip:
        return 0.0, track_duration, "whole-track"
    lo = max(10.0, 0.08 * track_duration)
    hi = track_duration - clip - max(20.0, 0.10 * track_duration)
    if hi <= lo:
        start = track_duration / 3.0
        return start, min(clip, track_duration - start), "one-third"
    return lo + start_fraction * (hi - lo), clip, "window"


def ffmpeg_argv(ffmpeg: str, real_path: str, start: float, clip: float, out_path: str,
                fmt: str = "aac") -> list[str]:
    """The exact FFmpeg template of spec §10. Only variables: path, start, duration, format."""
    spec = OUTPUT_FORMATS[fmt]
    fade_out_st = max(0.0, clip - FADE_OUT_S)
    afade = f"afade=t=in:st=0:d={FADE_IN_S},afade=t=out:st={fade_out_st:.3f}:d={FADE_OUT_S}"
    return [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "1",
        "-protocol_whitelist", "file",
        "-ss", f"{start:.3f}", "-i", "file:" + real_path, "-t", f"{clip:.3f}",
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-ac", "2", "-ar", "48000", "-af", afade,
        *spec["codec_args"],
        out_path,
    ]  # fmt: skip


def golden_argv(argv: list[str], real_path: str, out_path: str) -> str:
    """argv as a printable line, with the path placeholders (no file names in the console)."""
    shown = []
    for a in argv:
        if a == "file:" + real_path:
            a = "file:<ABS_PATH>"
        elif a == out_path:
            a = "<TMPDIR>/" + "clip" + os.path.splitext(out_path)[1]
        elif a == argv[0]:
            a = os.path.basename(a)
        shown.append(a)
    return " ".join(shown)


def check_magic(head: bytes, fmt: str) -> bool:
    if fmt == "aac":
        return len(head) >= 8 and head[4:8] == b"ftyp"
    if fmt == "opus":
        return head[:4] == b"OggS"
    return False


def mp4_top_level_atoms(path: str) -> list[tuple[str, int, int]]:
    """List (type, offset, size) of top-level ISO-BMFF boxes."""
    atoms = []
    file_size = os.path.getsize(path)
    with open(path, "rb") as fh:
        offset = 0
        while offset + 8 <= file_size:
            fh.seek(offset)
            header = fh.read(16)
            size = int.from_bytes(header[0:4], "big")
            kind = header[4:8].decode("latin-1")
            if size == 1:
                size = int.from_bytes(header[8:16], "big")
            elif size == 0:
                size = file_size - offset
            if size < 8:
                break
            atoms.append((kind, offset, size))
            offset += size
    return atoms


def moov_position(path: str) -> str:
    """'start' (moov before mdat, faststart), 'end' (moov after mdat) or 'unknown'."""
    kinds = [a[0] for a in mp4_top_level_atoms(path)]
    if "moov" in kinds and "mdat" in kinds:
        return "start" if kinds.index("moov") < kinds.index("mdat") else "end"
    return "unknown"


# --------------------------------------------------------------------------------------------
# Small stats helpers
# --------------------------------------------------------------------------------------------


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (conservative on small samples)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return ordered[rank - 1]


def fmt_ms(v: float | None) -> str:
    return "-" if v is None else f"{v:.0f}"


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def safe_rmtree(path: str) -> None:
    """Remove a tree without ever descending into a symlink or junction (removes the link)."""
    if not os.path.lexists(path):
        return
    stack = [(path, False)]
    while stack:
        current, visited = stack.pop()
        if visited:
            os.rmdir(current)
            continue
        stack.append((current, True))
        with os.scandir(current) as it:
            for entry in it:
                if entry.is_symlink() or os.path.isjunction(entry.path):
                    # On Windows os.unlink removes file links, directory links and junctions
                    # (RemoveDirectoryW for the latter) without touching the target.
                    os.unlink(entry.path)
                elif entry.is_dir(follow_symlinks=False):
                    stack.append((entry.path, False))
                else:
                    try:
                        os.unlink(entry.path)
                    except PermissionError:
                        os.chmod(entry.path, stat.S_IWRITE)
                        os.unlink(entry.path)


# --------------------------------------------------------------------------------------------
# One synchronous prepare (ffprobe -> start point -> ffmpeg), used by the benches
# --------------------------------------------------------------------------------------------

# Candidate hardening (NOT in the spec template): only these demuxers may open an input.
# Demuxer names as FFmpeg reports them; mov covers mp4/m4a, ogg covers opus/oga.
DEMUXER_WHITELIST = "mp3,flac,wav,mov,mp4,m4a,ogg,aiff,asf,aac"


def prepare_clip(ffmpeg: str, ffprobe: str, real_path: str, start_fraction: float, clip: float,
                 out_dir: str, fmt: str = "aac", hardened: bool = False,
                 measure_estimated: bool = True) -> dict:
    """Run steps 3-5 of the spec §10 pipeline plus the spike's two additions:

    - duration check: when ffprobe says it estimated the duration from the bitrate, the real
      duration is measured (demux only) before the start point rule is applied;
    - output check: the clip is probed; empty or < 50 % of the planned length -> DECODE_ERROR;
      shorter than planned - 0.25 s (source ends early: truncated file, wrong header) -> the
      clip is encoded again from the source with the MEASURED length, so the fade-out sits
      at the real end instead of being cut off.

    measure_estimated=False keeps the plain §10 behaviour (benches: show the problem).
    Raises JobError with a normalized code.
    """
    t0 = time.perf_counter()
    extra = ["-format_whitelist", DEMUXER_WHITELIST] if hardened else []
    info = probe(ffprobe, real_path, extra)
    measure_ms = 0.0
    if info.duration_estimated and measure_estimated:
        tm = time.perf_counter()
        info.duration_probed = info.duration
        info.duration = measure_duration(ffmpeg, real_path, extra)
        measure_ms = (time.perf_counter() - tm) * 1000
    t1 = time.perf_counter()
    start, clip_dur, rule = compute_start(info.duration, clip, start_fraction)
    planned = clip_dur
    out_path = os.path.join(out_dir, "clip" + OUTPUT_FORMATS[fmt]["suffix"])

    spent = {"encode": 0.0, "verify": 0.0}

    def encode(length: float) -> list[str]:
        te = time.perf_counter()
        argv = ffmpeg_argv(ffmpeg, real_path, start, length, out_path, fmt)
        if hardened:
            pos = argv.index("-protocol_whitelist")
            argv[pos:pos] = extra
        proc = run_tool(argv, FFMPEG_TIMEOUT_S)
        if proc.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
            raise JobError(DECODE_ERROR, "ffmpeg failed", proc.stderr.decode("utf-8", "replace"))
        spent["encode"] += (time.perf_counter() - te) * 1000
        return argv

    def out_duration() -> float | None:
        tv = time.perf_counter()
        out = run_tool(ffprobe_argv(ffprobe, out_path), FFPROBE_TIMEOUT_S)
        spent["verify"] += (time.perf_counter() - tv) * 1000
        return parse_probe(out.stdout.decode("utf-8", "replace")).duration

    argv = encode(clip_dur)
    out_dur = out_duration()
    reencoded = False
    if out_dur is None or out_dur < 0.5 * planned:
        raise JobError(DECODE_ERROR, "output clip empty or far too short (source ends early?)")
    if out_dur < planned - SHORT_CLIP_TOLERANCE_S:
        clip_dur = out_dur  # what the source really holds from `start`
        os.unlink(out_path)
        argv = encode(clip_dur)
        out_dur = out_duration()
        reencoded = True
        if out_dur is None or out_dur < 0.5 * planned:
            raise JobError(DECODE_ERROR, "re-encoded clip empty or far too short")
    return {
        "info": info, "start": start, "clip_duration": clip_dur, "planned_duration": planned,
        "out_duration": out_dur, "reencoded": reencoded, "rule": rule, "argv": argv,
        "out_path": out_path, "probe_ms": (t1 - t0) * 1000, "measure_ms": measure_ms,
        "encode_ms": spent["encode"], "verify_ms": spent["verify"],
        "bytes": os.path.getsize(out_path),
    }
