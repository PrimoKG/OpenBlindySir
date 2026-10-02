"""Clip upload by the Bridge and clip download by players (spec §5.3, §8.1)."""

import hashlib
import re

from fastapi import APIRouter, Request
from fastapi.responses import Response

from openblindysir_protocol.bridge import UPLOAD_SHA256_HEADER
from openblindysir_protocol.enums import AssetState
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.audio.magic import mime_for, sniff_magic
from openblindysir_server.auth.cookies import read_token
from openblindysir_server.game import commands as c
from openblindysir_server.logging import get, log_event
from openblindysir_server.security import error
from openblindysir_server.state import app_state

router = APIRouter()
LOG = get("audio")
ASSET_ID = re.compile(r"^a_[A-Za-z0-9_-]{22}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IN_FLIGHT = {AssetState.REQUESTED, AssetState.ENCODING, AssetState.UPLOADING}


@router.put("/api/bridge/assets/{asset_id}")
async def put_asset(asset_id: str, request: Request) -> Response:
    state = app_state(request)
    runtime = state.runtime
    if not ASSET_ID.match(asset_id):
        return error(404, ErrorCode.NOT_FOUND)
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    now = runtime.clock.now().mono_ms
    grant = (
        runtime.bridge.consume_upload_token(asset_id, token.strip(), now)
        if scheme.lower() == "bearer"
        else None
    )
    if grant is None:
        log_event(LOG, "upload_rejected", reason="token")
        return error(403, ErrorCode.UPLOAD_REJECTED)
    asset = runtime.engine.asset_info(asset_id)
    if asset is None or asset.state not in IN_FLIGHT:
        log_event(LOG, "upload_rejected", reason="state")
        return error(409, ErrorCode.UPLOAD_REJECTED)
    announced = request.headers.get(UPLOAD_SHA256_HEADER, "")
    if not SHA256.match(announced):
        runtime.dispatch(c.UploadRejected(asset_id))
        log_event(LOG, "upload_rejected", reason="sha256_header")
        return error(400, ErrorCode.UPLOAD_REJECTED)
    limit = runtime.cache.max_item_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        runtime.dispatch(c.UploadRejected(asset_id))
        log_event(LOG, "upload_rejected", reason="too_large")
        return error(413, ErrorCode.PAYLOAD_TOO_LARGE)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            runtime.dispatch(c.UploadRejected(asset_id))
            log_event(LOG, "upload_rejected", reason="too_large")
            return error(413, ErrorCode.PAYLOAD_TOO_LARGE)
    data = bytes(body)
    if not sniff_magic(state.settings.clip_format, data[:16]):
        runtime.dispatch(c.UploadRejected(asset_id))
        log_event(LOG, "upload_rejected", reason="magic")
        return error(400, ErrorCode.UPLOAD_REJECTED)
    digest = hashlib.sha256(data).hexdigest()
    if digest != announced:
        runtime.dispatch(c.UploadRejected(asset_id))
        log_event(LOG, "upload_rejected", reason="sha256")
        return error(400, ErrorCode.UPLOAD_REJECTED)
    roles = runtime.engine.retained_assets()
    keep = frozenset(a for a, role in roles.items() if role.value in ("current", "next"))
    result = runtime.cache.put_pending(
        asset_id, data, mime_for(state.settings.clip_format, data), keep
    )
    for evicted in result.evicted:
        if evicted in roles:
            runtime.dispatch(c.AssetEvicted(evicted))
    if not result.stored:
        runtime.dispatch(c.CacheRefused(asset_id))
        log_event(LOG, "upload_rejected", reason="cache_full")
        return error(507, ErrorCode.UPLOAD_REJECTED)
    runtime.dispatch(
        c.UploadVerified(asset_id, len(data), digest, mime_for(state.settings.clip_format, data))
    )
    return Response(status_code=204)


@router.get("/api/audio/{asset_id}")
async def get_audio(asset_id: str, request: Request) -> Response:
    """Only the current or next clip, never a partial upload; uniform 404 otherwise."""
    state = app_state(request)
    runtime = state.runtime
    pid = runtime.sessions.resolve(read_token(request, state.settings), runtime.clock.now().mono_ms)
    if pid is None or not runtime.engine.player_exists(pid):
        return error(401, ErrorCode.UNAUTHENTICATED)
    item = runtime.cache.get_servable(asset_id, runtime.engine.audio_servable())
    if item is None:
        return error(404, ErrorCode.NOT_FOUND)
    data, mime = item
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "no-store, private"},
    )
