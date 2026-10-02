#!/usr/bin/env python3
"""Repository hygiene check for OpenBlindySir.

OpenBlindySir must never publish music, real audio clips, local configuration or secrets.
This script fails (exit status 1, one message per problem) when a tracked file is:

- an audio file (or a video container that may carry music), detected by extension
  (case-insensitive) or by its magic bytes;
- a local environment file (``.env``, ``.env.*``, ``*.env``, ``.envrc``), ``.env.example``
  excepted;
- a private key or certificate (``*.pem``, ``*.key``, ``*.crt``, ``*.p12``, ``*.pfx``,
  ``id_rsa*``, ``id_ed25519*``...);
- inside a build, dependency or cache directory (``node_modules/``, ``dist/``, ``.venv/``...);
- larger than 5 MB;
- a text file (UTF-8, or UTF-16/UTF-32 with a byte order mark) containing an obvious secret:
  a PEM private key block, a GitHub, AWS or Slack token, or one of the server secret
  variables (``BLIND_PASSWORD``, ``HOST_PASSWORD``, ``BRIDGE_SECRET``, any case; ``secret``
  in a ``.toml`` file) assigned a value that is not a placeholder. In comments and
  documentation, only ``NAME=value`` counts, so prose such as ``HOST_PASSWORD: at least 12
  characters`` is not reported.

A placeholder is the whole value matching a closed list: empty, ``REPLACE_ME``,
``changeme``, ``example...``, ``your-...``, ``xxx``, ``***``, ``...``, ``<...>``, or a
variable reference (``${NAME}``, ``$NAME``, ``%NAME%``, ``${{ ... }}``). Test passwords in
fixtures, tests and CI files must therefore start with ``example`` (for instance
``example-host-password-1``).

In a git work tree, the files checked are the entries of the git index (``git ls-files``),
and their content is read from the index, which is what the next commit will contain: stage
your changes before running the check. Outside a git repository, or when nothing is tracked
yet (before ``git init`` or the first ``git add``), the directory tree is walked instead,
skipping ``.git``, virtual environments, dependency, build and cache directories. That
fallback does not read ``.gitignore``, so it is stricter than the git mode.

A line containing the marker ``hygiene: allow`` is exempt from the content checks; use it
only for documented false positives, never to keep a real value.

Standard library only, Python 3.12 or newer. Exit status: 0 when clean, 1 when problems
are found, 2 on usage or environment errors.
"""

from __future__ import annotations

import argparse
import codecs
import io
import os
import re
import stat
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ALLOW_MARKER = "hygiene: allow"
MAX_FILE_BYTES = 5 * 1024 * 1024
BINARY_SNIFF_BYTES = 8192
MAGIC_BYTES_LEN = 12

AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp3", ".flac", ".wav", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".oga", ".wma",
        ".aiff", ".aif", ".webm", ".mka", ".ape", ".wv", ".dsf", ".dff", ".mp2", ".mpa",
        ".caf", ".ac3", ".amr", ".au", ".snd",
        # Video containers often carry music (clips, music videos).
        ".mp4", ".m4v", ".mov", ".3gp",
    }
)  # fmt: skip

# ISO base media (MP4/QuickTime/3GP) major brands that denote audio or video content.
# Image brands such as heic or avif are deliberately absent.
MP4_AUDIO_BRANDS: tuple[bytes, ...] = (b"M4A", b"M4B", b"M4P")  # compared on 3 bytes
MP4_VIDEO_BRANDS: frozenset[bytes] = frozenset(
    {
        b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"M4V ", b"dash",
        b"3gp4", b"3gp5", b"3gp6", b"qt  ",
    }
)  # fmt: skip

# Repository-relative POSIX paths of audio files that are explicitly allowed, for example a
# freely licensed fixture whose licence is documented next to it. Empty on purpose: tests
# generate their sounds at runtime.
AUDIO_ALLOWLIST: frozenset[str] = frozenset()

KEY_EXTENSIONS: frozenset[str] = frozenset({".pem", ".key", ".crt", ".p12", ".pfx"})
KEY_NAME_PREFIXES: tuple[str, ...] = ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")
COMPILED_PYTHON_EXTENSIONS: frozenset[str] = frozenset({".pyc", ".pyo"})

# Directories whose content must never be tracked (compared case-insensitively).
FORBIDDEN_DIRS: frozenset[str] = frozenset(
    {
        "node_modules", "dist", "build", ".venv", "venv", "__pycache__", "playwright-report",
        "test-results", "coverage", "htmlcov", ".pytest_cache", ".ruff_cache", ".mypy_cache",
        ".pyright", ".local",
    }
)  # fmt: skip
WALK_SKIP_DIRS: frozenset[str] = FORBIDDEN_DIRS | {".git"}

# In documentation, as in comments, only NAME=value counts as an assignment: prose such as
# "HOST_PASSWORD: at least 12 characters" is not reported.
DOC_SUFFIXES: frozenset[str] = frozenset({".md", ".rst", ".adoc"})
DOC_DIRS: frozenset[str] = frozenset({"docs"})

# In source code, an unquoted right-hand side is an expression, not a literal secret.
CODE_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
)

COMMENT_PREFIXES: tuple[str, ...] = ("#", "//", ";", "--", "*", "rem ")

SECRET_VARIABLES: tuple[str, ...] = ("BLIND_PASSWORD", "HOST_PASSWORD", "BRIDGE_SECRET")

# The whole value (quotes removed) must match: a substring test would accept real
# passphrases such as "soiree-exchange-pizza-42".
PLACEHOLDER_RE = re.compile(
    r"(?i)(?:"
    r"replace[_-]?me|change[_-]?me|example[\w.-]*|your[_-][\w-]*|x{3,}|\*{3,}"
    r"|\.\.\.|\N{HORIZONTAL ELLIPSIS}|<[^>]*>"
    r"|\$\{[^}]*\}|\$[A-Za-z_]\w*|%[A-Za-z_]\w*%|\$\{\{.*\}\}"
    r")"
)

# A value: quoted string, ${{ ... }} expression, <placeholder with spaces>, or a bare word
# (which stops at a quote or a backtick, as in Markdown `NAME=value`).
_VALUE = r"(?P<value>\"[^\"]*\"|'[^']*'|\$\{\{[^}\n]*\}\}|<[^>\n]*>|[^\s#,;`'\"]*)"

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_{$%])"
    r"(?P<name>" + "|".join(SECRET_VARIABLES) + r")(?![A-Za-z0-9_])[\"']?\]?"
    r"(?P<sep>\s*[:=])(?!=)\s*" + _VALUE,
    re.IGNORECASE,
)

# In source code, "NAME: type = value": skip the annotation to reach the value.
ANNOTATED_VALUE_RE = re.compile(r"[\w\[\]., |]+?\s*=(?!=)\s*" + _VALUE)

# Dockerfile legacy form "ENV NAME value".
DOCKER_ENV_RE = re.compile(
    r"^\s*ENV\s+(?P<name>" + "|".join(SECRET_VARIABLES) + r")\s+" + _VALUE, re.IGNORECASE
)

# The Bridge config.toml stores its secret under a plain "secret" key.
TOML_SECRET_RE = re.compile(r"^\s*(?P<name>secret)\s*=\s*" + _VALUE, re.IGNORECASE)

EMPTY_BLOB_SHAS: frozenset[str] = frozenset(
    {
        "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        "473a0f4c3be8a93681a267e3b1e9a7dcda1185436fe141f7749120a303721813",
    }
)
REGULAR_BLOB_MODES: frozenset[str] = frozenset({"100644", "100755"})


@dataclass(frozen=True)
class SecretPattern:
    """A regular expression that reveals a well-known kind of secret on a single line."""

    label: str
    regex: re.Pattern[str]


# The patterns are written so that this file does not match itself.
SECRET_PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern(
        "private key block",
        re.compile(r"-{5}BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-{5}"),
    ),
    SecretPattern(
        "GitHub token",
        re.compile(r"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    ),
    SecretPattern(
        "AWS access key id",
        re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])"),
    ),
    SecretPattern(
        "Slack token",
        re.compile(r"(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{10,}"),
    ),
)


@dataclass(frozen=True, order=True)
class Finding:
    """One hygiene problem; ``line`` is 0 when the problem concerns the whole file."""

    path: str
    line: int
    reason: str

    def render(self) -> str:
        location = f"{self.path}:{self.line}" if self.line else self.path
        return f"{location}: {self.reason}"


# --------------------------------------------------------------------------------------------
# File listing
# --------------------------------------------------------------------------------------------


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    """Run a git command in ``root``; return None when git itself is unavailable."""
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    except OSError:
        return None


def git_toplevel(path: Path) -> Path | None:
    """Return the top-level directory of the git work tree containing ``path``, if any."""
    result = run_git(path, "rev-parse", "--show-toplevel")
    if result is None or result.returncode != 0:
        return None
    return Path(result.stdout.decode("utf-8", "surrogateescape").strip())


class HygieneError(Exception):
    """An environment error (git failure) that prevents the check from running."""


@dataclass(frozen=True, order=True)
class IndexEntry:
    """One entry of the git index: path relative to the root, file mode and object id."""

    path: str
    mode: str
    sha: str


def git_index_entries(root: Path) -> list[IndexEntry] | None:
    """List the git index entries under ``root``, relative to ``root`` (POSIX separators).

    A path in conflict appears once per stage, so that every version is checked.
    """
    result = run_git(root, "ls-files", "-z", "-s")
    if result is None or result.returncode != 0:
        return None
    entries: list[IndexEntry] = []
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        mode, sha, _stage = meta.decode("ascii").split()
        entries.append(IndexEntry(raw_path.decode("utf-8", "surrogateescape"), mode, sha))
    return sorted(entries)


class GitBlobReader:
    """Read blobs from the object database through one ``git cat-file --batch`` process.

    Returns ``(size, data)``: the whole content when it is at most ``limit`` bytes, otherwise
    only its first ``MAGIC_BYTES_LEN`` bytes (the rest is read and discarded).
    """

    def __init__(self, root: Path) -> None:
        try:
            self._process = subprocess.Popen(
                ["git", "-C", str(root), "cat-file", "--batch"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        except OSError as error:
            raise HygieneError(f"cannot run git cat-file ({error.strerror})") from error

    def __enter__(self) -> GitBlobReader:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        process = self._process
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()
        process.wait()

    def read(self, sha: str, limit: int) -> tuple[int, bytes] | None:
        """Return ``(size, data)`` for a blob, or None when the object is missing."""
        stdin, stdout = self._process.stdin, self._process.stdout
        assert stdin is not None
        assert stdout is not None
        try:
            stdin.write(sha.encode("ascii") + b"\n")
            stdin.flush()
            header = stdout.readline().split()
        except OSError as error:
            raise HygieneError(f"git cat-file failed ({error})") from error
        if len(header) == 2 and header[1] == b"missing":
            return (0, b"") if sha in EMPTY_BLOB_SHAS else None
        if len(header) != 3:
            raise HygieneError(f"unexpected git cat-file output for {sha}")
        size = int(header[2])
        keep = size if size <= limit else MAGIC_BYTES_LEN
        data = stdout.read(keep)
        remaining = size - len(data)
        while remaining > 0:
            chunk = stdout.read(min(remaining, 1 << 20))
            if not chunk:
                break
            remaining -= len(chunk)
        stdout.read(1)  # the LF that follows each object
        if remaining > 0 or len(data) < keep:
            raise HygieneError(f"truncated git cat-file output for {sha}")
        return size, data


def is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or os.path.isjunction(path)


def walk_files(root: Path) -> list[str]:
    """List every file under ``root``, skipping VCS, dependency, build and cache directories."""
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name.lower() not in WALK_SKIP_DIRS and not is_link_or_junction(current / name)
        )
        files.extend((current / name).relative_to(root).as_posix() for name in filenames)
    return sorted(files)


# --------------------------------------------------------------------------------------------
# Name-based checks
# --------------------------------------------------------------------------------------------


def is_audio_name(rel: PurePosixPath) -> bool:
    return rel.suffix.lower() in AUDIO_EXTENSIONS and rel.as_posix() not in AUDIO_ALLOWLIST


def is_env_file(name: str) -> bool:
    lowered = name.lower()
    if lowered == ".env.example":
        return False
    return lowered.startswith(".env.") or lowered.endswith(".env") or lowered == ".envrc"


def is_key_file(name: str) -> bool:
    lowered = name.lower()
    return PurePosixPath(lowered).suffix in KEY_EXTENSIONS or lowered.startswith(KEY_NAME_PREFIXES)


def forbidden_dir(rel: PurePosixPath) -> str | None:
    """Return the first build/dependency/cache directory found in the path, if any."""
    for part in rel.parts[:-1]:
        if part.lower() in FORBIDDEN_DIRS:
            return part
    return None


def check_name(rel: PurePosixPath) -> list[str]:
    """Problems that can be detected from the path alone."""
    reasons: list[str] = []
    directory = forbidden_dir(rel)
    if directory is not None:
        reasons.append(f"inside a build, dependency or cache directory ({directory}/)")
    if is_env_file(rel.name):
        reasons.append("local environment file (only .env.example may be tracked)")
    if is_key_file(rel.name):
        reasons.append("private key or certificate file")
    if rel.suffix.lower() in COMPILED_PYTHON_EXTENSIONS:
        reasons.append("compiled Python file")
    if is_audio_name(rel):
        reasons.append(f"audio or video file extension ({rel.suffix})")
    return reasons


# --------------------------------------------------------------------------------------------
# Content checks
# --------------------------------------------------------------------------------------------


def is_mpeg_audio_frame(head: bytes) -> bool:
    """MPEG audio frame header without ID3 tag (Layer II or III): sync word, valid rates.

    Layer I is not detected from content: a Layer I frame with CRC starts with FF FE, the
    UTF-16 LE byte order mark, so it cannot be told apart from a text file.
    """
    if len(head) < 3 or head[0] != 0xFF or head[1] & 0xE0 != 0xE0:
        return False
    version = (head[1] >> 3) & 0b11
    layer = (head[1] >> 1) & 0b11
    bitrate_index = head[2] >> 4
    sample_rate_index = (head[2] >> 2) & 0b11
    return (
        version != 0b01
        and layer in (0b01, 0b10)
        and bitrate_index not in (0x0, 0xF)
        and sample_rate_index != 0b11
    )


def is_adts_frame(head: bytes) -> bool:
    """Raw AAC (ADTS) frame header: 12-bit sync word, layer 00, valid sampling index."""
    if len(head) < 3 or head[0] != 0xFF or head[1] & 0xF6 != 0xF0:
        return False
    return (head[2] >> 2) & 0xF < 13


def detect_audio_signature(head: bytes) -> str | None:
    """Name the audio container recognised from the first bytes of a file, if any."""
    if head[:3] == b"ID3" and len(head) >= 5 and head[3] in (2, 3, 4) and head[4] != 0xFF:
        return "MP3 (ID3 tag)"
    if head[:4] == b"fLaC" and len(head) >= 5 and head[4] & 0x7F == 0:
        return "FLAC"
    if head[:4] == b"OggS" and len(head) >= 5 and head[4] == 0:
        return "Ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "WAV (RIFF)"
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return "AIFF"
    if head[4:8] == b"ftyp" and head[8:11] in MP4_AUDIO_BRANDS:
        return "MPEG-4 audio (ftyp M4A)"
    if head[4:8] == b"ftyp" and head[8:12] in MP4_VIDEO_BRANDS:
        return f"MPEG-4/QuickTime (ftyp {head[8:12].decode('ascii').strip()})"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "Matroska/WebM (EBML)"
    if head[:8] == b"\x30\x26\xb2\x75\x8e\x66\xcf\x11":
        return "ASF/WMA"
    if is_mpeg_audio_frame(head):
        return "MPEG audio frame"
    if is_adts_frame(head):
        return "AAC (ADTS)"
    return None


def decode_text(data: bytes) -> str | None:
    """Decode a text file (UTF-32/UTF-16 with BOM, else UTF-8); None for a binary file.

    The BOM test comes first: every UTF-16 or UTF-32 text contains NUL bytes.
    """
    if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        return data.decode("utf-32", errors="replace")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    if b"\0" in data[:BINARY_SNIFF_BYTES]:
        return None
    return data.decode("utf-8-sig", errors="replace")


def is_documentation(rel: PurePosixPath) -> bool:
    return rel.suffix.lower() in DOC_SUFFIXES or (
        len(rel.parts) > 1 and rel.parts[0].lower() in DOC_DIRS
    )


def is_dockerfile(rel: PurePosixPath) -> bool:
    lowered = rel.name.lower()
    return lowered.startswith(("dockerfile", "containerfile")) or lowered.endswith(".dockerfile")


def is_comment(line: str) -> bool:
    return line.lstrip("\ufeff \t").lower().startswith(COMMENT_PREFIXES)


def is_placeholder(value: str) -> bool:
    """True for an empty value or a whole value from the closed placeholder list."""
    return not value or PLACEHOLDER_RE.fullmatch(value) is not None


def unquote(raw: str) -> tuple[str, bool]:
    """Return the value without its quotes, and whether it was a quoted literal."""
    quoted = raw[:1] in ("'", '"')
    return raw.strip("'\"").strip(), quoted


def leaked_assignments(line: str, *, code_file: bool, doc_file: bool) -> list[str]:
    """Names of secret variables assigned a non-placeholder value on this line."""
    comment = is_comment(line)
    names: list[str] = []
    for match in SECRET_ASSIGNMENT_RE.finditer(line):
        raw = match.group("value")
        colon = match.group("sep").strip() == ":"
        if (comment or doc_file) and colon:
            continue  # prose such as "# BRIDGE_SECRET: at least 32 characters"
        if code_file and colon and raw[:1] not in ("'", '"'):
            annotated = ANNOTATED_VALUE_RE.match(line, match.start("value"))
            if annotated is not None:
                raw = annotated.group("value")  # NAME: str = "value"
        value, quoted = unquote(raw)
        if code_file and not quoted:
            continue  # an expression such as os.environ.get(...), not a literal
        if not is_placeholder(value):
            names.append(match.group("name"))
    return names


def leaked_special_forms(line: str, rel: PurePosixPath) -> list[str]:
    """Dockerfile ``ENV NAME value`` and the Bridge ``secret = "..."`` TOML key."""
    names: list[str] = []
    for regex, applies in (
        (DOCKER_ENV_RE, is_dockerfile(rel)),
        (TOML_SECRET_RE, rel.suffix.lower() == ".toml"),
    ):
        match = regex.match(line) if applies else None
        if match is not None and not is_placeholder(unquote(match.group("value"))[0]):
            names.append(match.group("name"))
    return names


def scan_text(rel: PurePosixPath, text: str) -> list[Finding]:
    """Look for obvious secrets, line by line, honouring the opt-out marker."""
    findings: list[Finding] = []
    path = rel.as_posix()
    doc_file = is_documentation(rel)
    code_file = rel.suffix.lower() in CODE_SUFFIXES
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.regex.search(line):
                findings.append(Finding(path, number, f"possible {pattern.label}"))
        names = leaked_assignments(line, code_file=code_file, doc_file=doc_file)
        names.extend(leaked_special_forms(line, rel))
        for name in names:
            reason = f"{name} assigned a value that is not a placeholder"
            findings.append(Finding(path, number, reason))
    return findings


USES_LINE = re.compile(r"^\s*(-\s*)?uses:\s*(?P<target>\S+)")
PINNED_USES = re.compile(r"^\s*(-\s*)?uses:\s*[^@\s]+@[0-9a-f]{40}\s+#\s*v\S+")


def is_workflow_file(rel: PurePosixPath) -> bool:
    """GitHub Actions workflow files, whose actions must be pinned (spec §12 supply chain)."""
    parts = rel.parts
    return (
        len(parts) == 3
        and parts[:2] == (".github", "workflows")
        and rel.suffix.lower() in {".yml", ".yaml"}
    )


def check_actions_pinned(rel: PurePosixPath, text: str) -> list[Finding]:
    """Every non-local ``uses:`` must be pinned to a 40-hex commit SHA with a version comment."""
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = USES_LINE.match(line)
        if not match or match.group("target").startswith("./"):
            continue
        if not PINNED_USES.match(line):
            reason = "action not pinned to a full commit SHA with a '# vX.Y.Z' comment"
            findings.append(Finding(rel.as_posix(), number, reason))
    return findings


def read_content(path: Path, size: int) -> bytes:
    """Read the whole file when it is small enough to scan, otherwise only its magic bytes."""
    with path.open("rb") as handle:
        return handle.read() if size <= MAX_FILE_BYTES else handle.read(MAGIC_BYTES_LEN)


def check_data(rel: PurePosixPath, size: int, data: bytes) -> list[Finding]:
    """Problems found in a file's content: size, audio magic bytes, secrets.

    ``data`` holds the whole content when ``size`` is at most MAX_FILE_BYTES, otherwise only
    its first MAGIC_BYTES_LEN bytes.
    """
    path = rel.as_posix()
    findings: list[Finding] = []
    if size > MAX_FILE_BYTES:
        reason = f"file too large ({size:,} bytes, limit {MAX_FILE_BYTES:,})"
        findings.append(Finding(path, 0, reason))
    signature = detect_audio_signature(data[:MAGIC_BYTES_LEN])
    if signature and not is_audio_name(rel) and path not in AUDIO_ALLOWLIST:
        findings.append(Finding(path, 0, f"audio content detected ({signature} magic bytes)"))
    if size <= MAX_FILE_BYTES:
        text = decode_text(data)
        if text is not None:
            findings.extend(scan_text(rel, text))
            if is_workflow_file(rel):
                findings.extend(check_actions_pinned(rel, text))
    return findings


def check_worktree_file(root: Path, relative: str) -> list[Finding]:
    """Directory-walk mode: name checks, then the content of the file on disk."""
    rel = PurePosixPath(relative)
    findings = [Finding(relative, 0, reason) for reason in check_name(rel)]
    full_path = root / relative
    try:
        info = full_path.lstat()
    except OSError:
        return findings  # vanished during the walk: name checks still apply
    if not stat.S_ISREG(info.st_mode):
        return findings  # symbolic link or special file: never followed
    try:
        data = read_content(full_path, info.st_size)
    except OSError as error:
        return [*findings, Finding(relative, 0, f"unreadable file ({error.strerror})")]
    findings.extend(check_data(rel, info.st_size, data))
    return findings


def check_index_entry(reader: GitBlobReader, entry: IndexEntry) -> list[Finding]:
    """Git mode: name checks, then the content staged in the index (what gets committed)."""
    rel = PurePosixPath(entry.path)
    findings = [Finding(entry.path, 0, reason) for reason in check_name(rel)]
    if entry.mode not in REGULAR_BLOB_MODES:
        return findings  # 120000 symbolic link or 160000 submodule: never followed
    blob = reader.read(entry.sha, MAX_FILE_BYTES)
    if blob is None:
        return [*findings, Finding(entry.path, 0, f"object {entry.sha} missing from git")]
    size, data = blob
    findings.extend(check_data(rel, size, data))
    return findings


def collect_findings(root: Path, *, verbose: bool) -> tuple[int, list[Finding]]:
    """Check the git index when ``root`` is in a work tree with tracked files, else walk.

    A work tree with no tracked file below ``root`` (fresh ``git init``, or an unrelated parent
    repository) falls back to the stricter tree walk instead of reporting an empty success.
    Returns the number of files checked and the findings, without duplicates.
    """
    toplevel = git_toplevel(root)
    entries = git_index_entries(root) if toplevel is not None else None
    findings: list[Finding] = []
    if entries:
        if verbose:
            print(f"hygiene: mode = git index (work tree {toplevel})")
        with GitBlobReader(root) as reader:
            for entry in entries:
                if verbose:
                    print(f"  checking {entry.path}")
                findings.extend(check_index_entry(reader, entry))
        return len({entry.path for entry in entries}), sorted(set(findings))
    if verbose:
        print("hygiene: mode = directory walk (no tracked files, .gitignore not applied)")
    files = walk_files(root)
    for relative in files:
        if verbose:
            print(f"  checking {relative}")
        findings.extend(check_worktree_file(root, relative))
    return len(files), sorted(set(findings))


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail when tracked files contain audio, .env files, keys or secrets.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="directory to check (default: the git top-level of this repository)",
    )
    parser.add_argument("--verbose", action="store_true", help="list every file checked")
    return parser.parse_args(argv)


def resolve_root(requested: Path | None) -> Path:
    """Use --root as given, otherwise the git top-level of this script's repository.

    Without git, the parent of the tools/ directory holding this script is used.
    """
    if requested is not None:
        return requested.resolve()
    default = Path(__file__).resolve().parent.parent
    toplevel = git_toplevel(default)
    return toplevel.resolve() if toplevel is not None and toplevel.resolve() == default else default


def configure_output() -> None:
    """Never crash on non-ASCII paths with a legacy Windows console encoding."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")


def main(argv: Sequence[str] | None = None) -> int:
    configure_output()
    if sys.version_info < (3, 12):  # noqa: UP036 - exit 2, not a traceback, on old Pythons
        print("hygiene: error: Python 3.12 or newer is required", file=sys.stderr)
        return 2
    args = parse_args(argv)
    root = resolve_root(args.root)
    if not root.is_dir():
        print(f"hygiene: error: {root} is not a directory", file=sys.stderr)
        return 2
    if args.verbose:
        print(f"hygiene: root = {root}")
    try:
        checked, findings = collect_findings(root, verbose=args.verbose)
    except HygieneError as error:
        print(f"hygiene: error: {error}", file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(finding.render())
        bad_files = len({finding.path for finding in findings})
        print(
            f"hygiene: FAILED ({len(findings)} problem(s) in {bad_files} file(s), "
            f"{checked} files checked)"
        )
        return 1
    print(f"hygiene: OK ({checked} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
