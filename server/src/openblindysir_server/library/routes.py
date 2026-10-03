"""Catalogue upload (``PUT /api/bridge/catalog``) and host library (``GET /api/host/library``)."""

import asyncio
import json
import zlib

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.requests import ClientDisconnect

from openblindysir_protocol.bridge import (
    BRIDGE_ID_HEADER,
    CATALOG_MAX_GZIP_BYTES,
    CATALOG_MAX_RAW_BYTES,
    CATALOG_TOKEN_HEADER,
    CatalogUpload,
)
from openblindysir_protocol.catalog_rules import compute_catalog_hash, compute_track_id
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.game import commands as c
from openblindysir_server.game.state import CatalogEntryData
from openblindysir_server.library.management import host_access
from openblindysir_server.logging import get, log_event
from openblindysir_server.security import UPLOAD_TIMEOUT_S, error
from openblindysir_server.state import app_state
from openblindysir_server.ws.bridge_link import ActiveBridge

router = APIRouter()
LOG = get("bridge")
MAX_TOTAL_LIBRARY_TRACKS = 200_000


class _TooLarge(Exception):
    pass


class _InvalidGzip(ValueError):
    pass


async def _read_gzip(request: Request) -> bytes:
    """Streamed read, compressed size capped, decompression capped (gzip bomb protection)."""
    received = 0
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = bytearray()
    async with asyncio.timeout(UPLOAD_TIMEOUT_S):
        async for chunk in request.stream():
            received += len(chunk)
            if received > CATALOG_MAX_GZIP_BYTES:
                raise _TooLarge
            out.extend(inflater.decompress(chunk, CATALOG_MAX_RAW_BYTES + 1 - len(out)))
            if len(out) > CATALOG_MAX_RAW_BYTES or inflater.unconsumed_tail:
                raise _TooLarge
            if inflater.unused_data:
                raise _InvalidGzip("invalid gzip stream")
    if not inflater.eof:
        raise _InvalidGzip("incomplete gzip stream")
    return bytes(out)


@router.put("/api/bridge/catalog")
async def put_catalog(request: Request) -> Response:
    state = app_state(request)
    runtime = state.runtime
    auth = request.headers.get("authorization", "")
    scheme, _, secret = auth.partition(" ")
    if scheme.lower() != "bearer":
        return error(401, ErrorCode.UNAUTHENTICATED)
    bridge_id = request.headers.get(BRIDGE_ID_HEADER)
    active = (
        runtime.bridge.connections.get(bridge_id)
        if bridge_id
        else (runtime.bridge.active if len(runtime.bridge.connections) == 1 else None)
    )
    token = request.headers.get(CATALOG_TOKEN_HEADER, "")
    now = runtime.clock.now().mono_ms
    if active is None:
        return error(403, ErrorCode.UPLOAD_REJECTED)
    try:
        authorized = runtime.credentials.authorize(active.bridge_id, secret.strip())
    except (OSError, ValueError):
        return error(503, ErrorCode.INVALID_STATE)
    if not authorized:
        return error(401, ErrorCode.UNAUTHENTICATED)
    with runtime.bridge.catalog_upload(active.bridge_id) as acquired:
        if not acquired:
            return error(429, ErrorCode.RATE_LIMITED)
        if not runtime.bridge.consume_catalog_token(active.bridge_id, token, now):
            return error(403, ErrorCode.UPLOAD_REJECTED)
        return await _receive_catalog(request, active)


async def _receive_catalog(request: Request, active: ActiveBridge) -> Response:
    state = app_state(request)
    runtime = state.runtime
    if request.headers.get("content-encoding", "").lower() != "gzip":
        return error(415, ErrorCode.JSON_REQUIRED)
    try:
        raw = await _read_gzip(request)
        upload = CatalogUpload.model_validate_json(raw)
    except _TooLarge:
        return error(413, ErrorCode.PAYLOAD_TOO_LARGE)
    except (TimeoutError, ClientDisconnect):
        return error(408, ErrorCode.INVALID_MESSAGE)
    except _InvalidGzip:
        return error(400, ErrorCode.INVALID_MESSAGE)
    except (zlib.error, ValidationError, UnicodeDecodeError) as exc:
        log_event(LOG, "catalog_rejected", reason="invalid_message", type=type(exc).__name__)
        return error(400, ErrorCode.INVALID_MESSAGE)
    if runtime.bridge.connections.get(active.bridge_id) is not active:
        return error(409, ErrorCode.UPLOAD_REJECTED)
    if not runtime.bridge_credentials_current(active):
        return error(409, ErrorCode.UPLOAD_REJECTED)
    if upload.bridge_id != active.bridge_id:
        return error(403, ErrorCode.UPLOAD_REJECTED)
    retained_tracks = sum(
        len(catalog.entries)
        for owner, catalog in runtime.engine.state.catalogs.items()
        if owner != active.bridge_id
    )
    if retained_tracks + len(upload.entries) > MAX_TOTAL_LIBRARY_TRACKS:
        return error(413, ErrorCode.PAYLOAD_TOO_LARGE)
    entries: dict[str, CatalogEntryData] = {}
    for entry in upload.entries:
        if entry.track_id != compute_track_id(entry.relpath) or entry.track_id in entries:
            log_event(LOG, "catalog_rejected", reason="track_id")
            return error(400, ErrorCode.INVALID_MESSAGE)
        entries[entry.track_id] = CatalogEntryData(
            entry.relpath, entry.folder, entry.ext, entry.size
        )
    if compute_catalog_hash(upload.entries) != upload.catalog_hash:
        log_event(LOG, "catalog_rejected", reason="hash")
        return error(400, ErrorCode.INVALID_MESSAGE)
    runtime.dispatch(
        c.CatalogLoaded(
            active.bridge_id,
            active.name,
            upload.catalog_hash,
            entries,
            tuple(upload.scanned_folders),
            upload.source_error,
            tuple(upload.ambiguous_paths),
        )
    )
    log_event(LOG, "catalog_received", tracks=len(entries), bytes=len(raw))
    return Response(status_code=204)


@router.get("/api/host/library")
async def get_library(request: Request) -> Response:
    state = app_state(request)
    runtime = state.runtime
    denied = host_access(request, state)
    if denied is not None:
        return denied
    view = runtime.engine.library().model_dump(mode="json")
    s = runtime.engine.state
    return JSONResponse(
        view,
        headers={
            "X-Catalog-Revisions": json.dumps(
                {bid: catalog.scan_revision for bid, catalog in s.catalogs.items()},
                separators=(",", ":"),
            )
        },
    )
