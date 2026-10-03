"""Library scanner (spec §11): one allowed root, never following symlinks nor junctions.

``os.walk`` is never used: it follows junctions on Windows. Hidden and system files are
skipped. No ffprobe at scan time.
"""

import os
import stat
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from openblindysir_protocol.media import INPUT_EXTENSIONS

DEFAULT_EXTENSIONS = INPUT_EXTENSIONS
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4


@dataclass(frozen=True, slots=True)
class LocalEntry:
    relpath: str  # POSIX separators, NFC: used for track_id and the catalogue
    fs_parts: tuple[str, ...]  # real names returned by scandir: used to reopen (macOS NFD)
    size: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class ScanResult:
    root_real: str
    entries: tuple[LocalEntry, ...]
    skipped_links: int
    skipped_hidden: int
    skipped_errors: int
    duration_s: float


def is_link_or_junction(path: str) -> bool:
    return os.path.islink(path) or os.path.isjunction(path)


def require_unlinked_path(
    path: Path, *, message: str = "path must not contain a link or junction"
) -> None:
    """Inspect the spelling before realpath can hide a linked ancestor."""
    absolute = path.absolute()
    if any(is_link_or_junction(str(part)) for part in (absolute, *absolute.parents)):
        raise ValueError(message)


def _hidden(entry: os.DirEntry[str]) -> bool:
    if entry.name.startswith("."):
        return True
    if sys.platform == "win32":
        attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attributes & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
    return False


def _confined(path: str, root_real: str) -> bool:
    real = os.path.realpath(path)
    try:
        common = os.path.commonpath([real, root_real])
    except ValueError:  # different drives on Windows
        return False
    return os.path.normcase(common) == os.path.normcase(root_real)


def scan(
    root: Path,
    extensions: frozenset[str] = DEFAULT_EXTENSIONS,
    *,
    max_files: int = 200_000,
    max_depth: int = 32,
) -> ScanResult:
    """Iterative scan of ``root``; entries sorted by relpath."""
    started = time.perf_counter()
    if not extensions <= INPUT_EXTENSIONS:
        raise ValueError("unsupported extensions")
    require_unlinked_path(root, message="root must not be a link or junction")
    root_real = os.path.realpath(root, strict=True)
    entries: list[LocalEntry] = []
    links = hidden = errors = 0
    stack: list[tuple[str, tuple[str, ...]]] = [(root_real, ())]
    while stack and len(entries) < max_files:
        directory, parts = stack.pop()
        try:
            iterator = os.scandir(directory)
        except OSError:
            errors += 1
            continue
        with iterator:
            for entry in iterator:
                try:
                    if _hidden(entry):
                        hidden += 1
                        continue
                    if entry.is_symlink() or os.path.isjunction(entry.path):
                        links += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if len(parts) < max_depth:
                            stack.append((entry.path, (*parts, entry.name)))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if os.path.splitext(entry.name)[1].lower() not in extensions:
                        continue
                    if not _confined(entry.path, root_real):
                        links += 1
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        continue
                    fs_parts = (*parts, entry.name)
                    relpath = unicodedata.normalize("NFC", "/".join(fs_parts))
                    entries.append(LocalEntry(relpath, fs_parts, info.st_size, info.st_mtime_ns))
                    if len(entries) >= max_files:
                        break
                except OSError:
                    errors += 1
    entries.sort(key=lambda e: e.relpath)
    return ScanResult(
        root_real=root_real,
        entries=tuple(entries),
        skipped_links=links,
        skipped_hidden=hidden,
        skipped_errors=errors,
        duration_s=time.perf_counter() - started,
    )
