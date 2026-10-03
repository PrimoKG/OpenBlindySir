"""Bridge WebSocket ``/api/bridge/ws`` (spec §8.3): Bearer secret, HELLO/WELCOME, jobs."""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from openblindysir_protocol.bridge import (
    BRIDGE_DEAD_S,
    BRIDGE_HEARTBEAT_S,
    BridgeHello,
    BridgeLimits,
    BridgePing,
    BridgePong,
    BridgeToServer,
    CatalogChanged,
    JobDone,
    JobFailed,
    JobProgress,
    Welcome,
)
from openblindysir_protocol.compatibility import Compatibility, mismatch_reason
from openblindysir_protocol.settings import WS_BRIDGE_MAX_BYTES
from openblindysir_protocol.text import normalize_nickname
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_server import __version__
from openblindysir_server.auth.bridges import secret_hash
from openblindysir_server.game import commands as c
from openblindysir_server.logging import get, log_event
from openblindysir_server.ratelimit import TokenBucket
from openblindysir_server.state import AppState, app_state, client_ip
from openblindysir_server.ws.bridge_link import ActiveBridge

router = APIRouter()
LOG = get("bridge")
INBOUND = TypeAdapter(BridgeToServer)
POLICY = 1008
TOO_BIG = 1009
HELLO_TIMEOUT_S = 5


def bearer(ws: WebSocket) -> str:
    header = ws.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def welcome(state: AppState, bridge_id: str, catalog_hash: str, *, force: bool = False) -> Welcome:
    runtime = state.runtime
    needed = force or runtime.engine.catalog_needed(bridge_id, catalog_hash)
    token = (
        runtime.bridge.issue_catalog_token(bridge_id, runtime.clock.now().mono_ms)
        if needed
        else None
    )
    settings = state.settings
    return Welcome(
        t="WELCOME",
        clip_format=settings.clip_format,
        bitrate=settings.clip_bitrate,
        limits=BridgeLimits(
            clip_min_s=float(settings.clip_min_s),
            clip_max_s=float(settings.clip_max_s),
            max_clip_bytes=settings.max_clip_mb * 1024 * 1024,
        ),
        catalog_needed=needed,
        catalog_upload_token=token,
        compatibility=Compatibility(server_version=__version__),
    )


def display_name(raw: str) -> str:
    try:
        return normalize_nickname(raw)
    except ValueError:
        return "Bridge"


async def _hello(ws: WebSocket) -> BridgeHello | None:
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=HELLO_TIMEOUT_S)
        msg = INBOUND.validate_json(raw) if len(raw) <= WS_BRIDGE_MAX_BYTES else None
    except (TimeoutError, WebSocketDisconnect, ValidationError, KeyError):
        return None
    return msg if isinstance(msg, BridgeHello) else None


@router.websocket("/api/bridge/ws")
async def bridge_ws(ws: WebSocket) -> None:
    state = app_state(ws)
    ip = client_ip(ws)
    now = state.runtime.clock.now().mono_ms
    if state.bridge_auth_limiter.blocked(ip, now):
        await ws.close(1013, "authentication rate limited")
        return
    try:
        accepted = state.runtime.credentials.recognizes(bearer(ws))
    except (OSError, ValueError):
        await ws.close(1011, "credential registry unavailable")
        return
    if not accepted:
        state.bridge_auth_limiter.record(ip, now)
        log_event(LOG, "bridge_rejected", reason="auth")
        await ws.close(POLICY)
        return
    if not state.bridge_counter.acquire(ip):
        await ws.close(1013, "connection limit")
        return
    try:
        await _serve_bridge(ws)
    finally:
        state.bridge_counter.release(ip)


async def _serve_bridge(ws: WebSocket) -> None:
    state: AppState = app_state(ws)
    runtime = state.runtime
    await ws.accept()
    hello = await _hello(ws)
    if hello is None or hello.protocol != PROTOCOL_VERSION:
        log_event(LOG, "bridge_rejected", reason="protocol")
        await ws.close(POLICY, mismatch_reason())
        return
    try:
        authorized = runtime.credentials.authorize(hello.bridge_id, bearer(ws), bind=True)
    except (OSError, ValueError):
        await ws.close(1011, "credential registry unavailable")
        return
    if not authorized:
        state.bridge_auth_limiter.record(client_ip(ws), runtime.clock.now().mono_ms)
        await ws.close(POLICY, "authentication")
        return
    if state.settings.clip_format not in hello.formats:
        log_event(LOG, "bridge_rejected", reason="format")
        await ws.close(POLICY)
        return
    if hello.bridge_id not in runtime.bridge.connections and len(runtime.bridge.connections) >= 8:
        await ws.close(POLICY, "bridge limit")
        return
    name = display_name(hello.name)
    bridge = ActiveBridge(hello.bridge_id, name, ws, runtime.clock.now().mono_ms)
    bridge.credential_hash = secret_hash(bearer(ws))
    previous = runtime.bridge.activate(bridge)
    if previous is not None:
        previous.request_close(1000, "replaced")
        runtime.dispatch(c.BridgeDisconnected(previous.bridge_id))
    writer = asyncio.create_task(bridge.writer())
    heartbeat = asyncio.create_task(_heartbeat(state, bridge))
    try:
        bridge.push(welcome(state, hello.bridge_id, hello.catalog_hash))
        runtime.dispatch(
            c.BridgeConnected(
                hello.bridge_id,
                name,
                hello.version,
                hello.catalog_hash,
                hello.track_count,
                hello.protocol,
                tuple(f.value for f in hello.formats),
                hello.allow_full_review,
            )
        )
        await _read_loop(state, bridge)
    finally:
        heartbeat.cancel()
        # Cancellation must not interrupt the synchronous ownership/state cleanup.
        if runtime.bridge.deactivate(bridge):
            runtime.dispatch(c.BridgeDisconnected(bridge.bridge_id))
        bridge.request_close(1000)
        await asyncio.gather(heartbeat, return_exceptions=True)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(writer, timeout=1)


async def _heartbeat(state: AppState, bridge: ActiveBridge) -> None:
    clock = state.runtime.clock
    while bridge.close_code is None:
        await asyncio.sleep(BRIDGE_HEARTBEAT_S)
        now = clock.now().mono_ms
        if now - bridge.last_rx_mono > BRIDGE_DEAD_S * 1000:
            log_event(LOG, "bridge_lost", bridge_id=bridge.bridge_id, reason="heartbeat")
            bridge.request_close(1001)
            return
        bridge.push(BridgePing(t="PING", c=float(clock.mono_ms_precise())))


async def _read_loop(state: AppState, bridge: ActiveBridge) -> None:
    runtime = state.runtime
    bucket = TokenBucket(40, 20, runtime.clock.now().mono_ms)
    while bridge.close_code is None:
        try:
            raw = await bridge.ws.receive_text()
        except (WebSocketDisconnect, RuntimeError):
            return
        except KeyError:
            bridge.request_close(1003)
            return
        now = runtime.clock.now()
        if not runtime.bridge_credentials_current(bridge):
            bridge.request_close(POLICY, "authentication")
            return
        bridge.last_rx_mono = now.mono_ms
        if not bucket.take(now.mono_ms):
            bridge.request_close(POLICY, "message rate limit")
            return
        if len(raw.encode("utf-8")) > WS_BRIDGE_MAX_BYTES:
            bridge.request_close(TOO_BIG)
            return
        try:
            msg = INBOUND.validate_json(raw)
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_input=False, include_context=False)
            first = errors[0] if errors else {}
            loc = ".".join(str(part) for part in first.get("loc", ()))
            log_event(LOG, "bridge_invalid_message", loc=loc, type=first.get("type", "?"))
            continue
        if runtime.bridge.connections.get(bridge.bridge_id) is not bridge:
            return
        match msg:
            case BridgePong() | BridgeHello():
                pass
            case CatalogChanged(catalog_hash=catalog_hash):
                bridge.push(welcome(state, bridge.bridge_id, catalog_hash, force=True))
            case JobProgress(job_id=job_id, stage=stage):
                if _owned(state, bridge, job_id) and not runtime.reviews.report(msg):
                    runtime.dispatch(c.JobProgressIn(job_id, stage), at=now)
            case JobDone(job_id=job_id):
                if _owned(state, bridge, job_id):
                    if not runtime.reviews.report(msg):
                        runtime.dispatch(c.JobDoneIn(msg), at=now)
                    runtime.bridge.job_owner.pop(job_id, None)
            case JobFailed(job_id=job_id, code=code):
                if _owned(state, bridge, job_id):
                    if not runtime.reviews.report(msg):
                        runtime.dispatch(c.JobFailedIn(job_id, code), at=now)
                    runtime.bridge.job_owner.pop(job_id, None)


def _owned(state: AppState, bridge: ActiveBridge, job_id: str) -> bool:
    if state.runtime.bridge.owns_job(bridge.bridge_id, job_id):
        return True
    log_event(LOG, "job_unknown", job_id=job_id)
    return False
