"""Private library search, safe source commands and validated optional metadata."""

import json
import posixpath
import time
import unicodedata
import zipfile
import zlib
from dataclasses import asdict, replace

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from openblindysir_protocol.bridge import ScanSources
from openblindysir_protocol.catalog_rules import compute_track_id
from openblindysir_protocol.enums import EndGameMode, GamePhase, HostMode
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.host_commands import (
    EndGameArgs,
    HostEndGame,
    HostFinalValidate,
    PublishArgs,
)
from openblindysir_protocol.http import LibrarySearch, LibraryTrack, MetadataEdit, SourceUpdate
from openblindysir_protocol.metadata import MetadataRow
from openblindysir_server.auth.routes import current_player
from openblindysir_server.game import commands as c
from openblindysir_server.game import rounds, selection
from openblindysir_server.game.auto_scoring import criteria
from openblindysir_server.game.metadata import musical_metadata
from openblindysir_server.game.state import AssetRecord, Metadata, SessionState, TrackRef
from openblindysir_server.library import metadata_archive
from openblindysir_server.security import check_origin, error, read_bounded_body, read_json_body
from openblindysir_server.state import AppState, app_state

router = APIRouter()
PRIVATE_PHASES = {GamePhase.LOBBY, GamePhase.FINAL_SCORE_REVIEW, GamePhase.FINAL_RESULTS}


@router.post("/api/host/game/finish")
async def finish_game(request: Request) -> Response:
    state = app_state(request)
    denied = host_access(request, state, mutation=True, library=False)
    if denied is not None:
        return denied
    raw = await read_json_body(request)
    if isinstance(raw, Response):
        return raw
    denied = host_access(request, state, mutation=True, library=False)
    if denied is not None:
        return denied
    try:
        payload = json.loads(raw)
        if (
            set(payload) != {"game_id", "phase", "confirm_unreviewed"}
            or payload["confirm_unreviewed"] is not True
        ):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        return error(400, ErrorCode.INVALID_ARGS)
    runtime = state.runtime
    game = runtime.engine.state.game
    if payload["game_id"] != game.game_id or payload["phase"] != game.phase.value:
        return error(409, ErrorCode.STALE_COMMAND)
    pid = current_player(request, state)
    assert pid is not None
    if game.phase is GamePhase.LOBBY:
        return error(409, ErrorCode.INVALID_STATE)
    if game.phase is GamePhase.IN_GAME:
        outcome = runtime.dispatch(
            c.HostIn(
                pid,
                HostEndGame(
                    t="HOST",
                    cmd="end_game",
                    expected_phase=game.phase,
                    args=EndGameArgs(current_round=EndGameMode.SCORE),
                ),
            )
        )
        if outcome.error:
            return error(409, outcome.error)
    if game.phase is GamePhase.FINAL_SCORE_REVIEW:
        outcome = runtime.dispatch(
            c.HostIn(
                pid,
                HostFinalValidate(
                    t="HOST",
                    cmd="final_validate",
                    expected_phase=GamePhase.FINAL_SCORE_REVIEW,
                    args=PublishArgs(confirm_unreviewed=True),
                ),
            )
        )
        if outcome.error:
            return error(409, outcome.error)
    game.podium_skipped = True
    runtime.engine.state.touched = True
    runtime.hub.mark_dirty()
    runtime.save_snapshot()
    return JSONResponse({"ok": True})


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
    activation: str = "all",
    quality: str = "all",
    pool_only: bool = False,
    tag: str = "",
    linked_to: str = "",
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
        or len(tag) > 256
        or len(linked_to) > 256
        or activation not in {"all", "active", "disabled"}
        or quality not in {"all", "ready", "missing"}
        or len(folder) > 1024
        or offset < 0
        or not 1 <= limit <= 100
        or sort not in {"title", "artist", "filename", "folder"}
        or availability
        not in {"all", "available", "unavailable", "online", "offline", "fresh", "used", "reserved"}
    ):
        return error(400, ErrorCode.INVALID_ARGS)
    pid = current_player(request, state)
    assert pid is not None
    now = state.runtime.clock.now().mono_ms
    if state.library_search_busy or not state.library_search_limiter.allow(pid, now):
        return error(429, ErrorCode.RATE_LIMITED)
    snapshot = search_snapshot(state.runtime.engine.state)
    state.library_search_busy = True
    try:
        response = await run_in_threadpool(
            search_response,
            snapshot,
            q=q,
            bridge=bridge,
            folder=folder,
            ext=ext,
            availability=availability,
            activation=activation,
            quality=quality,
            pool_only=pool_only,
            tag=tag,
            linked_to=linked_to,
            offset=offset,
            limit=limit,
            sort=sort,
            descending=descending,
        )
        # The role, phase, session or cookie can change while the worker runs.
        denied = host_access(request, state)
        if denied is not None:
            return denied
        if snapshot.epoch != state.runtime.engine.state.epoch:
            return error(409, ErrorCode.STALE_COMMAND)
        return response
    finally:
        state.library_search_busy = False


def search_snapshot(s: SessionState) -> SessionState:
    """Detach mutable containers before handing the search to a worker.

    Catalogue entries are frozen records. Metadata rows/lists are replaced (COW)
    by import/edit, never mutated in place. No worker accesses a live dictionary.
    Only small mutable bridge/asset records need copying, not the game history.
    """
    return replace(
        s,
        catalogs={bid: replace(c, entries=c.entries.copy()) for bid, c in s.catalogs.items()},
        bridges={bid: replace(b) for bid, b in s.bridges.items()},
        metadata=s.metadata.copy(),
        imported_metadata=s.imported_metadata.copy(),
        assets={aid: replace(a) for aid, a in s.assets.items()},
        played=s.played.copy(),
        consumed_cancelled=s.consumed_cancelled.copy(),
        game=replace(
            s.game,
            settings=replace(s.game.settings, sources=list(s.game.settings.sources)),
            unavailable=s.game.unavailable.copy(),
            manual_tracks=s.game.manual_tracks.copy(),
            pipeline=[replace(slot) for slot in s.game.pipeline],
            rounds=[replace(r, slot=replace(r.slot)) for r in s.game.rounds],
        ),
    )


def search_response(
    s: SessionState,
    *,
    q: str,
    bridge: str,
    folder: str,
    ext: str,
    availability: str,
    activation: str,
    tag: str,
    linked_to: str,
    offset: int,
    limit: int,
    sort: str,
    descending: bool,
    quality: str = "all",
    pool_only: bool = False,
) -> Response:
    found: list[tuple[tuple[str, str, str], TrackRef]] = []
    sources = tuple(s.game.settings.sources)
    reserved = set(s.game.manual_tracks.values()) | {
        slot.track_ref for slot in selection.live_slots(s)
    }
    measured = {a.track_ref: a for a in s.assets.values() if a.track_duration_ms is not None}
    query = normalized(q)
    tag_query, link_query = normalized(tag), normalized(linked_to)
    total = 0
    tags: dict[str, str] = {}
    links: dict[str, str] = {}
    scanned = 0
    for b, catalog in sorted(s.catalogs.items()):
        if bridge and b != bridge:
            continue
        online = s.bridges.get(b) is not None and s.bridges[b].state.value == "ONLINE"
        for tid, entry in sorted(catalog.entries.items()):
            scanned += 1
            if scanned % 256 == 0:
                # Yield the GIL in the worker so a CPU-heavy catalogue cannot
                # monopolize HTTP/WS threads. This never sleeps on the network loop.
                time.sleep(0.001)
            ref = TrackRef(b, tid)
            if pool_only and not any(
                ref.bridge_id == owner and selection.matches(entry.relpath, prefix)
                for owner, prefix in sources
            ):
                continue
            meta = musical_metadata(s, ref)
            for label in meta.tags or []:
                tags.setdefault(normalized(label), label)
            for label in meta.linked_to or []:
                links.setdefault(normalized(label), label)
            enabled = meta.enabled is not False
            if (activation == "active" and not enabled) or (activation == "disabled" and enabled):
                continue
            if tag_query and tag_query not in {normalized(value) for value in meta.tags or []}:
                continue
            if link_query and link_query not in {
                normalized(value) for value in meta.linked_to or []
            }:
                continue
            asset = measured.get(ref)
            missing = missing_references(s, meta, asset)
            if (quality == "ready" and missing) or (quality == "missing" and not missing):
                continue
            title = (
                None
                if "title" in (meta.cleared_fields or [])
                else meta.title or (asset.title if asset else None)
            )
            artist = (
                None
                if "artist" in (meta.cleared_fields or [])
                else meta.artist or (asset.artist if asset else None)
            )
            available = online and enabled and ref not in s.game.unavailable
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
            if query not in normalized(
                " ".join(
                    [
                        entry.relpath,
                        title or "",
                        artist or "",
                        *(meta.tags or []),
                        *(meta.linked_to or []),
                    ]
                )
            ):
                continue
            total += 1
            filename = posixpath.basename(entry.relpath)
            sort_value = {
                "title": title,
                "artist": artist,
                "filename": filename,
                "folder": entry.folder,
            }[sort]
            found.append(((normalized(sort_value or filename), b, tid), ref))
    found.sort(key=lambda hit: hit[0], reverse=descending)
    tracks = [
        search_track(s, ref, measured.get(ref), reserved, sources)
        for _, ref in found[offset : offset + limit]
    ]
    return JSONResponse(
        LibrarySearch(
            total=total,
            tracks=tracks,
            tags=sorted(tags.values(), key=normalized),
            linked_to=sorted(links.values(), key=normalized),
        ).model_dump(mode="json")
    )


def missing_references(s: SessionState, meta: Metadata, asset: AssetRecord | None) -> list[str]:
    return [
        key
        for key in criteria(s.game.settings)
        if key == "custom"
        or key in (meta.cleared_fields or [])
        or not (
            getattr(meta, key, None) or getattr(asset, key, None) or (meta.aliases or {}).get(key)
        )
    ]


def search_track(
    s: SessionState,
    ref: TrackRef,
    asset: AssetRecord | None,
    reserved: set[TrackRef | None],
    sources: tuple[tuple[str, str], ...],
) -> LibraryTrack:
    catalog = s.catalogs[ref.bridge_id]
    entry = catalog.entries[ref.track_id]
    meta = musical_metadata(s, ref)
    enabled = meta.enabled is not False
    online = (
        s.bridges.get(ref.bridge_id) is not None
        and s.bridges[ref.bridge_id].state.value == "ONLINE"
    )
    return LibraryTrack(
        metadata_revision=s.metadata_revision,
        cleared_fields=meta.cleared_fields or [],
        missing_references=missing_references(s, meta, asset),
        aliases=meta.aliases,
        enabled=enabled,
        tags=meta.tags or [],
        linked_to=meta.linked_to or [],
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
        in_pool=enabled
        and ref not in s.game.unavailable
        and any(
            ref.bridge_id == owner and selection.matches(entry.relpath, prefix)
            for owner, prefix in sources
        ),
        bridge_id=ref.bridge_id,
        track_id=ref.track_id,
        filename=posixpath.basename(entry.relpath),
        folder=entry.folder,
        ext=entry.ext,
        available=online and enabled and ref not in s.game.unavailable,
        title=None
        if "title" in (meta.cleared_fields or [])
        else meta.title or (asset.title if asset else None),
        artist=None
        if "artist" in (meta.cleared_fields or [])
        else meta.artist or (asset.artist if asset else None),
        featuring=meta.featuring,
        album=meta.album,
        year=meta.year,
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
            or doc["version"] not in {1, 2}
            or not isinstance(doc["rows"], list)
            or len(doc["rows"]) > 10000
        ):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        return error(400, ErrorCode.INVALID_MESSAGE)
    return apply_metadata(state, doc)


def apply_metadata(state: AppState, doc: dict) -> Response:
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
        s.imported_metadata[ref] = Metadata(
            **{
                **asdict(s.imported_metadata.get(ref, Metadata())),
                **row.model_dump(exclude={"bridge_id", "relpath"}, exclude_unset=True),
            }
        )
        changed.add(ref)
        accepted += 1
    s.metadata_issues = issues
    if accepted:
        s.metadata_revision += 1
    selection.prune_manual_plans(s)
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
    raw = await read_json_body(request, limit=24 * 1024)
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
    if payload.expected_revision is not None and payload.expected_revision != s.metadata_revision:
        return error(409, ErrorCode.STALE_COMMAND)
    if not selection.track_exists(s, ref):
        return error(404, ErrorCode.NOT_FOUND)
    s.metadata[ref] = Metadata(
        **{
            **asdict(s.metadata.get(ref, Metadata())),
            **payload.metadata.model_dump(exclude_unset=True),
        }
    )
    s.metadata_revision += 1
    selection.prune_manual_plans(s)
    if s.game.phase is GamePhase.FINAL_SCORE_REVIEW:
        for r in s.game.rounds:
            if r.slot.track_ref == ref and r.reveal is not None:
                r.reveal = rounds.build_reveal(s, r)
                r.metadata_revision += 1
    state.runtime.hub.mark_dirty()
    state.runtime.save_snapshot()
    return JSONResponse({"ok": True})


@router.get("/api/host/metadata")
async def export_metadata(request: Request, offset: int = 0) -> Response:
    state = app_state(request)
    denied = host_access(request, state)
    if denied is not None:
        return denied
    rows = metadata_rows(state.runtime.engine.state)
    if not 0 <= offset <= len(rows):
        return error(400, ErrorCode.INVALID_ARGS)
    content, end = metadata_archive.json_chunk(rows, offset)
    return Response(
        content,
        media_type="application/json",
        headers={
            "X-Next-Offset": str(end) if end < len(rows) else "",
            "X-Metadata-Total": str(len(rows)),
        },
    )


def metadata_rows(s: SessionState) -> list[dict]:
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
                        for name in (
                            "title",
                            "artist",
                            "featuring",
                            "album",
                            "year",
                            "tags",
                            "linked_to",
                            "enabled",
                            "aliases",
                            "cleared_fields",
                        )
                    },
                }
            )
    return rows


@router.get("/api/host/metadata/export")
async def export_metadata_pack(request: Request, offset: int = 0) -> Response:
    state = app_state(request)
    denied = host_access(request, state)
    if denied is not None:
        return denied
    if state.library_search_busy:
        return error(429, ErrorCode.RATE_LIMITED)
    snapshot = search_snapshot(state.runtime.engine.state)
    state.library_search_busy = True
    try:
        rows = await run_in_threadpool(metadata_rows, snapshot)
        if not 0 <= offset <= len(rows):
            return error(400, ErrorCode.INVALID_ARGS)
        content, end = await run_in_threadpool(metadata_archive.pack, rows, offset)
        denied = host_access(request, state)
        if denied is not None:
            return denied
        if snapshot.epoch != state.runtime.engine.state.epoch:
            return error(409, ErrorCode.STALE_COMMAND)
        return Response(
            content,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="openblindysir-metadata-{offset + 1}.zip"'
                ),
                "X-Next-Offset": str(end) if end < len(rows) else "",
                "X-Metadata-Total": str(len(rows)),
            },
        )
    finally:
        state.library_search_busy = False


@router.post("/api/host/metadata/import-archive")
async def import_metadata_pack(request: Request) -> Response:
    state = app_state(request)
    denied = host_access(request, state, mutation=True)
    if denied is not None:
        return denied
    if request.headers.get("content-type", "").split(";")[0] != "application/zip":
        return error(415, ErrorCode.INVALID_ARGS)
    raw = await read_bounded_body(request, metadata_archive.PACK_LIMIT, timeout_s=15)
    if isinstance(raw, Response):
        return raw
    if state.library_search_busy:
        return error(429, ErrorCode.RATE_LIMITED)
    epoch = state.runtime.engine.state.epoch
    state.library_search_busy = True
    try:
        try:
            doc = await run_in_threadpool(metadata_archive.unpack, raw)
        except (
            ValueError,
            TypeError,
            RecursionError,
            OSError,
            zipfile.BadZipFile,
            RuntimeError,
            NotImplementedError,
            zlib.error,
        ):
            return error(400, ErrorCode.INVALID_MESSAGE)
        denied = host_access(request, state, mutation=True)
        if denied is not None:
            return denied
        if epoch != state.runtime.engine.state.epoch:
            return error(409, ErrorCode.STALE_COMMAND)
        return apply_metadata(state, doc)
    finally:
        state.library_search_busy = False
