"""Catalogue upload (``PUT /api/bridge/catalog``) and host library (``GET /api/host/library``)."""

import zlib

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from openblindysir_protocol.bridge import (
    CATALOG_MAX_GZIP_BYTES,
    CATALOG_MAX_RAW_BYTES,
    CATALOG_TOKEN_HEADER,
    CatalogUpload,
)
from openblindysir_protocol.catalog_rules import compute_catalog_hash, compute_track_id
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.auth.cookies import read_token
from openblindysir_server.auth.sessions import verify_password
from openblindysir_server.game import commands as c
from openblindysir_server.game.state import CatalogEntryData
from openblindysir_server.logging import get, log_event
from openblindysir_server.security import error
from openblindysir_server.state import app_state

router = APIRouter()
LOG = get("bridge")


class _TooLarge(Exception):
    pass


async def _read_gzip(request: Request) -> bytes:
    """Streamed read, compressed size capped, decompression capped (gzip bomb protection)."""
    received = 0
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = bytearray()
    async for chunk in request.stream():
        received += len(chunk)
        if received > CATALOG_MAX_GZIP_BYTES:
            raise _TooLarge
        out.extend(inflater.decompress(chunk, CATALOG_MAX_RAW_BYTES + 1 - len(out)))
        if len(out) > CATALOG_MAX_RAW_BYTES or inflater.unconsumed_tail:
            raise _TooLarge
    out.extend(inflater.flush())
    if len(out) > CATALOG_MAX_RAW_BYTES:
        raise _TooLarge
    return bytes(out)


@router.put("/api/bridge/catalog")
async def put_catalog(request: Request) -> Response:
    state = app_state(request)
    runtime = state.runtime
    auth = request.headers.get("authorization", "")
    scheme, _, secret = auth.partition(" ")
    if scheme.lower() != "bearer" or not verify_password(
        secret.strip(), state.settings.bridge_secret
    ):
        return error(401, ErrorCode.UNAUTHENTICATED)
    active = runtime.bridge.active
    token = request.headers.get(CATALOG_TOKEN_HEADER, "")
    now = runtime.clock.now().mono_ms
    if active is None or not runtime.bridge.consume_catalog_token(active.bridge_id, token, now):
        return error(403, ErrorCode.UPLOAD_REJECTED)
    if request.headers.get("content-encoding", "").lower() != "gzip":
        return error(415, ErrorCode.JSON_REQUIRED)
    try:
        raw = await _read_gzip(request)
        upload = CatalogUpload.model_validate_json(raw)
    except _TooLarge:
        return error(413, ErrorCode.PAYLOAD_TOO_LARGE)
    except (zlib.error, ValidationError, UnicodeDecodeError) as exc:
        log_event(LOG, "catalog_rejected", reason="invalid_message", type=type(exc).__name__)
        return error(400, ErrorCode.INVALID_MESSAGE)
    if upload.bridge_id != active.bridge_id:
        return error(403, ErrorCode.UPLOAD_REJECTED)
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
    runtime.dispatch(c.CatalogLoaded(active.bridge_id, active.name, upload.catalog_hash, entries))
    log_event(LOG, "catalog_received", tracks=len(entries), bytes=len(raw))
    return Response(status_code=204)


@router.get("/api/host/library")
async def get_library(request: Request) -> Response:
    state = app_state(request)
    runtime = state.runtime
    pid = runtime.sessions.resolve(read_token(request, state.settings), runtime.clock.now().mono_ms)
    if pid is None or not runtime.engine.player_exists(pid):
        return error(401, ErrorCode.UNAUTHENTICATED)
    if not runtime.engine.is_host(pid):
        return error(403, ErrorCode.NOT_HOST)
    return JSONResponse(runtime.engine.library().model_dump(mode="json"))
