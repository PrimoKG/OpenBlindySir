"""Bridge catalogues: folder tree for the host (no file names) and display helpers."""

import posixpath
import unicodedata

from openblindysir_protocol.enums import BridgeState
from openblindysir_protocol.http import FolderNode, LibraryBridge, LibraryIssue, LibraryResponse
from openblindysir_server.game.metadata import musical_metadata
from openblindysir_server.game.state import Catalog, CatalogEntryData, SessionState, TrackRef


def file_display_name(entry: CatalogEntryData) -> str:
    """File name without extension, NFC."""
    base = posixpath.basename(entry.relpath)
    stem, _ext = posixpath.splitext(base)
    return unicodedata.normalize("NFC", stem or base)


def file_name(entry: CatalogEntryData) -> str:
    return posixpath.basename(entry.relpath)


def folder_tree(catalog: Catalog, s: SessionState | None = None) -> FolderNode:
    """Recursive folder tree with recursive track counts; folders only, never file names."""
    counts: dict[str, int] = {"": 0}
    children: dict[str, set[str]] = {"": set()}
    fresh: dict[str, int] = {}
    available: dict[str, int] = {}
    info = s.bridges.get(catalog.bridge_id) if s is not None else None
    online = s is None or (info is not None and info.state is BridgeState.ONLINE)
    for track_id, entry in catalog.entries.items():
        folder = entry.folder
        segments = folder.split("/") if folder else []
        counts[""] += 1
        ref = TrackRef(catalog.bridge_id, track_id)
        usable = online and (
            s is None
            or (ref not in s.game.unavailable and musical_metadata(s, ref).enabled is not False)
        )
        new = usable and (s is None or ref not in s.played)
        available[""] = available.get("", 0) + int(usable)
        fresh[""] = fresh.get("", 0) + int(new)
        prefix = ""
        for segment in segments:
            parent = prefix
            prefix = f"{prefix}/{segment}" if prefix else segment
            children.setdefault(parent, set()).add(prefix)
            children.setdefault(prefix, set())
            counts[prefix] = counts.get(prefix, 0) + 1
            available[prefix] = available.get(prefix, 0) + int(usable)
            fresh[prefix] = fresh.get(prefix, 0) + int(new)

    def build(prefix: str) -> FolderNode:
        name = prefix.rsplit("/", 1)[-1] if prefix else catalog.bridge_name
        return FolderNode(
            name=name,
            prefix=prefix,
            track_count=counts.get(prefix, 0),
            children=[build(child) for child in sorted(children.get(prefix, ()))],
            fresh_count=fresh.get(prefix, 0),
            available_count=available.get(prefix, 0),
        )

    return build("")


def library_response(s: SessionState) -> LibraryResponse:
    bridges: list[LibraryBridge] = []
    for bridge_id in sorted(s.catalogs):
        catalog = s.catalogs[bridge_id]
        info = s.bridges.get(bridge_id)
        bridges.append(
            LibraryBridge(
                bridge_id=bridge_id,
                name=catalog.bridge_name,
                online=info is not None and info.state is BridgeState.ONLINE,
                track_count=len(catalog.entries),
                root=folder_tree(catalog, s),
                scanned_folders=catalog.scanned_folders,
                source_error=catalog.source_error,
            )
        )
    issues: list[LibraryIssue] = []
    for catalog in s.catalogs.values():
        issues.extend(
            LibraryIssue(
                bridge_id=catalog.bridge_id,
                filename=posixpath.basename(path),
                folder=posixpath.dirname(path),
                code="ambiguous_path",
            )
            for path in catalog.ambiguous_paths
        )
    for ref in sorted(s.game.unavailable):
        catalog = s.catalogs.get(ref.bridge_id)
        entry = catalog.entries.get(ref.track_id) if catalog else None
        failed = next(
            (
                asset
                for asset in reversed(list(s.assets.values()))
                if asset.track_ref == ref and asset.error is not None
            ),
            None,
        )
        if entry:
            issues.append(
                LibraryIssue(
                    bridge_id=ref.bridge_id,
                    filename=file_name(entry),
                    folder=entry.folder,
                    code=failed.error.value if failed and failed.error else "decode_error",
                )
            )
    return LibraryResponse(bridges=bridges, issues=issues)
