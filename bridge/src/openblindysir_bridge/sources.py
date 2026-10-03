"""Scan only directories inside the locally authorized root; identities stay root-relative."""

import os
from dataclasses import replace
from pathlib import Path

from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.scanner import DEFAULT_EXTENSIONS, is_link_or_junction, scan
from openblindysir_protocol.settings import check_relative_path


def scan_sources(
    root: Path, folders: tuple[str, ...], extensions: frozenset[str] = DEFAULT_EXTENSIONS
) -> LocalCatalog:
    root_real = os.path.realpath(root, strict=True)
    for prefix in folders:
        check_relative_path(prefix, allow_empty=True)
        if ":" in prefix:
            raise ValueError("invalid folder")
        path = root_real
        for part in prefix.split("/") if prefix else ():
            path = os.path.join(path, part)
            if is_link_or_junction(path):
                raise ValueError("invalid folder")
        if (
            not os.path.isdir(path)
            or os.path.commonpath([os.path.realpath(path), root_real]) != root_real
        ):
            raise OSError("inaccessible folder")
    # A single traversal prevents duplicates and keeps IDs unchanged when folders overlap.
    result = scan(root, extensions)
    entries = tuple(
        e for e in result.entries if any(not f or e.relpath.startswith(f + "/") for f in folders)
    )
    catalog = LocalCatalog.from_scan(replace(result, entries=entries))
    return replace(catalog, scanned_folders=folders)
