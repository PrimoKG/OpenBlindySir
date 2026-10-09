"""Local catalogue: track_id → entry; the server only ever designates a dictionary key."""

import gzip
import posixpath
from dataclasses import dataclass, field

from openblindysir_bridge.scanner import LocalEntry, ScanResult
from openblindysir_protocol.bridge import CatalogEntry, CatalogUpload, Tags
from openblindysir_protocol.catalog_rules import compute_catalog_hash, compute_track_id
from openblindysir_protocol.settings import check_relative_path


@dataclass(frozen=True, slots=True)
class LocalCatalog:
    entries: dict[str, LocalEntry]  # track_id -> entry
    catalog_hash: str
    dropped: int  # collisions or names the protocol cannot carry
    scanned_folders: tuple[str, ...] = ("",)
    source_error: str | None = None
    ambiguous_paths: tuple[str, ...] = ()
    metadata: dict[str, Tags] = field(default_factory=dict)

    @classmethod
    def from_scan(cls, result: ScanResult) -> "LocalCatalog":
        entries: dict[str, LocalEntry] = {}
        ambiguous: set[str] = set()
        dropped = 0
        for entry in result.entries:
            try:
                check_relative_path(entry.relpath, allow_empty=False)
            except ValueError:
                dropped += 1
                continue
            track_id = compute_track_id(entry.relpath)
            if entry.relpath in ambiguous:
                dropped += 1
                continue
            if track_id in entries:
                previous = entries.pop(track_id)
                ambiguous.update((previous.relpath, entry.relpath))
                dropped += 2
                continue
            entries[track_id] = entry
        rows = [(tid, e.relpath, e.size) for tid, e in entries.items()]
        return cls(
            entries=entries,
            catalog_hash=compute_catalog_hash(rows),
            dropped=dropped,
            ambiguous_paths=tuple(sorted(ambiguous)),
        )

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
                    tags=self.metadata.get(tid),
                )
                for tid, entry in sorted(self.entries.items())
            ],
            scanned_folders=list(self.scanned_folders),
            source_error=self.source_error,  # type: ignore[arg-type]
            ambiguous_paths=list(self.ambiguous_paths),
        )
        return gzip.compress(upload.model_dump_json().encode("utf-8"), mtime=0)
