"""Catalogue identity rules shared by the Bridge (producer) and the server (verifier)."""

import hashlib
from collections.abc import Iterable

from openblindysir_protocol.bridge import CatalogEntry


def compute_track_id(relpath: str) -> str:
    """Stable, opaque track identifier: ``"t_" + sha256(relpath)[:16]`` (spec §11)."""
    return "t_" + hashlib.sha256(relpath.encode("utf-8")).hexdigest()[:16]


def compute_catalog_hash(entries: Iterable[CatalogEntry | tuple[str, str, int]]) -> str:
    """Order-independent hash of a catalogue: sha256 of ``track_id\\trelpath\\tsize\\n`` lines
    sorted by track id."""
    rows: list[tuple[str, str, int]] = []
    for entry in entries:
        if isinstance(entry, CatalogEntry):
            rows.append((entry.track_id, entry.relpath, entry.size))
        else:
            rows.append(entry)
    rows.sort()
    digest = hashlib.sha256()
    for track_id, relpath, size in rows:
        digest.update(f"{track_id}\t{relpath}\t{size}\n".encode())
    return digest.hexdigest()
