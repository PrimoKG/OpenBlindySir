"""Local catalogue: track_id → entry; the server only ever designates a dictionary key."""

import gzip
import posixpath
from dataclasses import dataclass

from openblindysir_bridge.scanner import LocalEntry, ScanResult
from openblindysir_protocol.bridge import CatalogEntry, CatalogUpload
from openblindysir_protocol.catalog_rules import compute_catalog_hash, compute_track_id
from openblindysir_protocol.settings import check_relative_path


@dataclass(frozen=True, slots=True)
class LocalCatalog:
    entries: dict[str, LocalEntry]  # track_id -> entry
    catalog_hash: str
    dropped: int  # collisions or names the protocol cannot carry

    @classmethod
    def from_scan(cls, result: ScanResult) -> "LocalCatalog":
        entries: dict[str, LocalEntry] = {}
        dropped = 0
        for entry in result.entries:
            try:
                check_relative_path(entry.relpath, allow_empty=False)
            except ValueError:
                dropped += 1
                continue
            track_id = compute_track_id(entry.relpath)
            if track_id in entries:
                dropped += 1
                continue
            entries[track_id] = entry
        rows = [(tid, e.relpath, e.size) for tid, e in entries.items()]
        return cls(entries=entries, catalog_hash=compute_catalog_hash(rows), dropped=dropped)

    def lookup(self, track_id: str) -> LocalEntry | None:
        return self.entries.get(track_id)

    def to_upload(self, bridge_id: str) -> bytes:
        """Deterministic gzip body of ``PUT /api/bridge/catalog``."""
        upload = CatalogUpload(
            bridge_id=bridge_id,
            catalog_hash=self.catalog_hash,
            entries=[
                CatalogEntry(
                    track_id=tid,
                    relpath=entry.relpath,
                    folder=posixpath.dirname(entry.relpath),
                    ext=posixpath.splitext(entry.relpath)[1].lower(),
                    size=entry.size,
                )
                for tid, entry in sorted(self.entries.items())
            ],
        )
        return gzip.compress(upload.model_dump_json().encode("utf-8"), mtime=0)
