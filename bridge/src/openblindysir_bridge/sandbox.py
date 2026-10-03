"""Confinement checks before EVERY file open (spec §11, ADR 0002).

A fresh realpath, confinement under the root, no link or junction on the way, a regular
file whose size and mtime still match the scan. The residual TOCTOU window is accepted.
"""

import os
import stat
from pathlib import Path

from openblindysir_bridge.scanner import LocalEntry, is_link_or_junction, require_unlinked_path


class SandboxError(Exception):
    """The entry cannot be opened safely; reported to the server as NOT_FOUND only."""


class Sandbox:
    def __init__(self, root_real: str) -> None:
        require_unlinked_path(Path(root_real))
        self.root_real = os.path.realpath(root_real, strict=True)

    def resolve_for_open(self, entry: LocalEntry) -> str:
        path = self.root_real
        for part in entry.fs_parts:
            if part in ("", ".", "..") or "/" in part or "\\" in part or "\x00" in part:
                raise SandboxError("invalid path component")
            path = os.path.join(path, part)
            if is_link_or_junction(path):
                raise SandboxError("link or junction on the path")
        try:
            real = os.path.realpath(path, strict=True)
        except OSError as exc:
            raise SandboxError("missing") from exc
        try:
            common = os.path.commonpath([real, self.root_real])
        except ValueError as exc:
            raise SandboxError("outside the root") from exc
        if os.path.normcase(common) != os.path.normcase(self.root_real):
            raise SandboxError("outside the root")
        try:
            info = os.stat(real)
        except OSError as exc:
            raise SandboxError("missing") from exc
        if not stat.S_ISREG(info.st_mode):
            raise SandboxError("not a regular file")
        if info.st_size != entry.size or info.st_mtime_ns != entry.mtime_ns:
            raise SandboxError("changed since the scan")
        return real
