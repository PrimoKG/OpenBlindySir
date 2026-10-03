"""Private library search, safe source commands and validated optional metadata."""

import json
import posixpath
import unicodedata

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from openblindysir_protocol.bridge import ScanSources
from openblindysir_protocol.catalog_rules import compute_track_id
from openblindysir_protocol.enums import GamePhase, HostMode
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.http import LibrarySearch, LibraryTrack, MetadataEdit, SourceUpdate
from openblindysir_protocol.metadata import MetadataRow
from openblindysir_server.auth.routes import current_player
from openblindysir_server.game import rounds, selection
from openblindysir_server.game.metadata import musical_metadata
from openblindysir_server.game.state import Metadata, TrackRef
from openblindysir_server.security import check_origin, error, read_json_body
from openblindysir_server.state import AppState, app_state

router = APIRouter()
PRIVATE_PHASES = {GamePhase.LOBBY, GamePhase.FINAL_SCORE_REVIEW, GamePhase.FINAL_RESULTS}


def host_access(
    request: Request, state: AppState, *, mutation: bool = False, library: bool = True
) -> Response | None:
    pid = current_player(request, state)
    if pid is None:
        return error(401, ErrorCode.UNAUTHENTICATED)
    if not state.runtime.engine.is_host(pid):
        return error(403, ErrorCode.NOT_HOST)
    if mutation and not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    s = state.runtime.engine.state
    if (
        library
        and s.game.phase not in PRIVATE_PHASES
        and s.players[pid].host_mode is not HostMode.MC
    ):
        return error(409, ErrorCode.INVALID_STATE)
    return None


def normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold().strip()


@router.get("/api/host/library/search")
async def search(
    request: Request,
    *,
    q: str = "",
    bridge: str = "",
    folder: str = "",
    ext: str = "",
    availability: str = "all",
    offset: int = 0,
    limit: int = 100,
    sort: str = "filename",
    descending: bool = False,
) -> Response:
    state = app_state(request)
    denied = host_access(request, state)
    if denied is not None:
        return denied
    if (
        len(q) > 256
        or len(folder) > 1024
        or offset < 0
        or not 1 <= limit <= 100
        or sort not in {"title", "artist", "filename", "folder"}
        or availability
        not in {"all", "available", "unavailable", "online", "offline", "fresh", "used", "reserved"}
    ):
        return error(400, ErrorCode.INVALID_ARGS)
    s = state.runtime.engine.state
    found: list[LibraryTrack] = []
    pool = set(selection.pool(s))
    reserved = set(s.game.manual_tracks.values()) | {
        slot.track_ref for slot in selection.live_slots(s)
    }
    measured = {a.track_ref: a for a in s.assets.values() if a.track_duration_ms is not None}
    total = 0
    for b, catalog in sorted(s.catalogs.items()):
        if bridge and b != bridge:
            continue
        online = s.bridges.get(b) is not None and s.bridges[b].state.value == "ONLINE"
        for tid, entry in sorted(catalog.entries.items()):
            ref = TrackRef(b, tid)
            meta = musical_metadata(s, ref)
            asset = measured.get(ref)
            title = meta.title or (asset.title if asset else None)
            artist = meta.artist or (asset.artist if asset else None)
            available = online and ref not in s.game.unavailable
            if folder and not selection.matches(entry.relpath, folder):
                continue
            if ext and entry.ext != ext:
                continue
            if (
                (availability == "available" and not available)
                or (availability == "unavailable" and available)
                or (availability == "online" and not online)
                or (availability == "offline" and online)
                or (availability == "fresh" and (not available or ref in s.played))
                or (availability == "used" and ref not in s.played)
                or (availability == "reserved" and (ref not in reserved or ref in s.played))
            ):
                continue
            if normalized(q) not in normalized(
                " ".join([entry.relpath, title or "", artist or ""])
            ):
                continue
            total += 1
            found.append(
                LibraryTrack(
                    consumption=(
                        "cancelled"
                        if ref in s.consumed_cancelled
                        else "played"
                        if ref in s.played
                        else "reserved"
                        if ref in reserved
                        else "available"
                    ),
                    bridge_name=catalog.bridge_name,
                    duration_ms=asset.track_duration_ms if asset else None,
                    played=ref in s.played,
                    reserved=ref in reserved and ref not in s.played,
                    in_pool=ref in pool,
                    bridge_id=b,
                    track_id=tid,
                    filename=posixpath.basename(entry.relpath),
                    folder=entry.folder,
                    ext=entry.ext,
                    available=available,
                    title=title,
                    artist=artist,
                    featuring=meta.featuring,
                    album=meta.album,
                    year=meta.year,
                )
            )
    found.sort(
        key=lambda track: (
            normalized(getattr(track, sort) or track.filename),
            track.bridge_id,
            track.track_id,
        ),
        reverse=descending,
    )
    return JSONResponse(
        LibrarySearch(total=total, tracks=found[offset : offset + limit]).model_dump(mode="json")
    )


@router.post("/api/host/library/sources")
async def update_sources(request: Request) -> Response:
    state = app_state(request)
    denied = host_access(request, state, mutation=True, library=False)
    if denied is not None:
        return denied
    raw = await read_json_body(request, limit=65536)
    if isinstance(raw, Response):
        return raw
    denied = host_access(request, state, mutation=True, library=False)
    if denied is not None:
        return denied
    try:
        payload = SourceUpdate.model_validate_json(raw)
        command = ScanSources(t="SCAN_SOURCES", folders=payload.folders)
    except ValidationError:
        return error(400, ErrorCode.INVALID_ARGS)
    bridge = state.runtime.bridge.connections.get(payload.bridge_id)
    if bridge is None:
        return error(503, ErrorCode.BRIDGE_OFFLINE)
    catalog = state.runtime.engine.state.catalogs.get(payload.bridge_id)
    bridge.push(command)
    return JSONResponse(
        {
            "ok": True,
            "status": "requested",
            "scan_revision": catalog.scan_revision if catalog else 0,
        },
        status_code=202,
    )


@router.post("/api/host/metadata/import")
async def import_metadata(request: Request) -> Response:
    state = app_state(request)
    denied = host_access(request, state, mutation=True)
    if denied is not None:
        return denied
    raw = await read_json_body(request, limit=1024 * 1024)
    if isinstance(raw, Response):
        return raw
    denied = host_access(request, state, mutation=True)
    if denied is not None:
        return denied
    try:
        doc = json.loads(raw)
        if (
            set(doc) != {"version", "rows"}
            or type(doc["version"]) is not int
            or doc["version"] != 1
            or not isinstance(doc["rows"], list)
            or len(doc["rows"]) > 10000
        ):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        return error(400, ErrorCode.INVALID_MESSAGE)
    s = state.runtime.engine.state
    seen: set[TrackRef] = set()
    changed: set[TrackRef] = set()
    issues = []
    accepted = 0
    for line, raw_row in enumerate(doc["rows"], 1):
        try:
            row = MetadataRow.model_validate(raw_row)
        except ValidationError:
            issues.append({"row": line, "code": "invalid"})
            continue
        ref = TrackRef(row.bridge_id, compute_track_id(row.relpath))
        catalog = s.catalogs.get(row.bridge_id)
        if catalog and row.relpath in catalog.ambiguous_paths:
            issues.append({"row": line, "code": "ambiguous"})
            continue
        if ref in seen:
            issues.append({"row": line, "code": "duplicate"})
            continue
        seen.add(ref)
        if (
            catalog is None
            or ref.track_id not in catalog.entries
            or catalog.entries[ref.track_id].relpath != row.relpath
        ):
            issues.append({"row": line, "code": "unknown"})
            continue
        s.imported_metadata[ref] = Metadata(**row.model_dump(exclude={"bridge_id", "relpath"}))
        changed.add(ref)
        accepted += 1
    s.metadata_issues = issues
    if s.game.phase is GamePhase.FINAL_SCORE_REVIEW:
        for r in s.game.rounds:
            if r.reveal is not None and r.slot.track_ref in changed:
                r.reveal = rounds.build_reveal(s, r)
                r.metadata_revision += 1
    state.runtime.hub.mark_dirty()
    state.runtime.save_snapshot()
    return JSONResponse({"accepted": accepted, "issues": issues})


@router.put("/api/host/metadata")
async def edit_metadata(request: Request) -> Response:
    state = app_state(request)
    denied = host_access(request, state, mutation=True)
    if denied is not None:
        return denied
    raw = await read_json_body(request)
    if isinstance(raw, Response):
        return raw
    denied = host_access(request, state, mutation=True)
    if denied is not None:
        return denied
    try:
        payload = MetadataEdit.model_validate_json(raw)
    except ValidationError:
        return error(400, ErrorCode.INVALID_ARGS)
    s = state.runtime.engine.state
    ref = TrackRef(payload.bridge_id, payload.track_id)
    if not selection.track_exists(s, ref):
        return error(404, ErrorCode.NOT_FOUND)
    s.metadata[ref] = Metadata(**payload.metadata.model_dump())
    if s.game.phase is GamePhase.FINAL_SCORE_REVIEW:
        for r in s.game.rounds:
            if r.slot.track_ref == ref and r.reveal is not None:
                r.reveal = rounds.build_reveal(s, r)
                r.metadata_revision += 1
    state.runtime.hub.mark_dirty()
    state.runtime.save_snapshot()
    return JSONResponse({"ok": True})


@router.get("/api/host/metadata")
async def export_metadata(request: Request) -> Response:
    state = app_state(request)
    denied = host_access(request, state)
    if denied is not None:
        return denied
    s = state.runtime.engine.state
    rows = []
    for ref in sorted(s.imported_metadata.keys() | s.metadata.keys()):
        metadata = musical_metadata(s, ref)
        catalog = s.catalogs.get(ref.bridge_id)
        entry = catalog.entries.get(ref.track_id) if catalog else None
        if entry is not None:
            rows.append(
                {
                    "bridge_id": ref.bridge_id,
                    "relpath": entry.relpath,
                    **{
                        name: getattr(metadata, name)
                        for name in ("title", "artist", "featuring", "album", "year")
                    },
                }
            )
    return JSONResponse({"version": 1, "rows": rows})
