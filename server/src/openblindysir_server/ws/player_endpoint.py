"""Player WebSocket ``/api/ws`` (spec §8.2).

The clock is read right after each frame is received, before parsing or any other await:
that instant timestamps ANSWER_SUBMIT (spec §6.3) and PONG.
"""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from openblindysir_protocol.client import (
    AnswerDraft,
    AnswerSubmit,
    AudioStatus,
    ClientMessage,
    Hello,
    Ping,
    PlaybackReport,
)
from openblindysir_protocol.compatibility import Compatibility, mismatch_reason
from openblindysir_protocol.errors import CloseCode, ErrorCode
from openblindysir_protocol.server import ErrorMsg, Pong
from openblindysir_protocol.settings import WS_PLAYER_MAX_BYTES
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_server import __version__
from openblindysir_server.auth.cookies import read_token
from openblindysir_server.game import commands as c
from openblindysir_server.logging import get, log_event
from openblindysir_server.ratelimit import TokenBucket
from openblindysir_server.security import browser_family, check_origin, truncate_ip
from openblindysir_server.state import AppState, app_state, client_ip
from openblindysir_server.ws.hub import PlayerConnection, log_refused

router = APIRouter()
LOG = get("ws")
CLIENT = TypeAdapter(ClientMessage)
HELLO_TIMEOUT_S = 5
POLICY = 1008
TOO_BIG = 1009
MAX_DROPPED = 200


def parse_client(raw: str) -> object | ValidationError:
    try:
        return CLIENT.validate_json(raw)
    except ValidationError as exc:
        return exc


def log_invalid(exc: ValidationError) -> None:
    errors = exc.errors(include_url=False, include_input=False, include_context=False)
    first = errors[0] if errors else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    log_event(LOG, "ws_invalid_message", loc=loc, type=first.get("type", "?"), count=len(errors))


async def _send_error_and_close(ws: WebSocket, code: ErrorCode, close: int) -> None:
    with contextlib.suppress(Exception):
        await ws.send_text(ErrorMsg(t="ERROR", code=code).model_dump_json())
        await ws.close(close)


async def _await_hello(ws: WebSocket) -> bool:
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=HELLO_TIMEOUT_S)
    except (TimeoutError, WebSocketDisconnect, KeyError):
        await _send_error_and_close(ws, ErrorCode.HELLO_REQUIRED, POLICY)
        return False
    msg = parse_client(raw) if len(raw) <= WS_PLAYER_MAX_BYTES else None
    if not isinstance(msg, Hello):
        await _send_error_and_close(ws, ErrorCode.HELLO_REQUIRED, POLICY)
        return False
    if msg.protocol != PROTOCOL_VERSION:
        await ws.send_text(
            ErrorMsg(
                t="ERROR",
                code=ErrorCode.PROTOCOL_MISMATCH,
                compatibility=Compatibility(server_version=__version__),
            ).model_dump_json()
        )
        await ws.close(POLICY, mismatch_reason())
        return False
    return True


@router.websocket("/api/ws")
async def player_ws(ws: WebSocket) -> None:
    state: AppState = app_state(ws)
    runtime = state.runtime
    ip = client_ip(ws)
    now = runtime.clock.now().mono_ms
    player_id = runtime.sessions.resolve(read_token(ws, state.settings), now)
    if not check_origin(ws.headers.get("origin"), state.settings):
        log_refused("origin", truncate_ip(ip))
        await ws.close(POLICY)
        return
    if player_id is None or not runtime.engine.player_exists(player_id):
        log_refused("unauthenticated", truncate_ip(ip))
        await ws.close(POLICY)
        return
    if not state.ws_counter.acquire(ip):
        log_refused("too_many_connections", truncate_ip(ip))
        await ws.close(POLICY)
        return
    try:
        await ws.accept()
        if not await _await_hello(ws):
            return
        hello_at = runtime.clock.now().mono_ms
        if runtime.sessions.resolve(
            read_token(ws, state.settings), hello_at
        ) != player_id or not runtime.engine.player_exists(player_id):
            await _send_error_and_close(ws, ErrorCode.UNAUTHENTICATED, POLICY)
            return
        conn = PlayerConnection(
            conn_id=runtime.hub.next_conn_id(),
            player_id=player_id,
            ws=ws,
            ip=ip,
            browser_family=browser_family(ws.headers.get("user-agent")),
            last_rx_mono=hello_at,
            bucket=TokenBucket(40, 20, hello_at),
        )
        previous = runtime.hub.register(conn)
        if previous is not None:
            previous.request_close(int(CloseCode.SUPERSEDED))
            log_event(LOG, "player_superseded", player_id=player_id)
        writer = asyncio.create_task(conn.writer())
        try:
            runtime.dispatch(c.Connected(player_id, "web"))
            runtime.hub.send_state_now(player_id)
            await _read_loop(state, conn)
        finally:
            if runtime.hub.unregister(conn):
                runtime.dispatch(c.Disconnected(player_id))
            conn.request_close(1000)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer, timeout=1)
    finally:
        state.ws_counter.release(ip)


async def _read_loop(state: AppState, conn: PlayerConnection) -> None:
    runtime = state.runtime
    pid = conn.player_id
    while conn.close_code is None:
        try:
            raw = await conn.ws.receive_text()
        except (WebSocketDisconnect, RuntimeError):
            return
        except KeyError:
            conn.request_close(1003)
            return
        now = runtime.clock.now()  # read HERE, before parsing or any other await
        precise = runtime.clock.mono_ms_precise()
        conn.last_rx_mono = now.mono_ms
        runtime.sessions.touch_player(pid, now.mono_ms)
        if len(raw.encode("utf-8")) > WS_PLAYER_MAX_BYTES:
            conn.push_critical(
                ErrorMsg(t="ERROR", code=ErrorCode.MESSAGE_TOO_LARGE).model_dump_json()
            )
            conn.request_close(TOO_BIG)
            return
        if not conn.bucket.take(now.mono_ms):
            conn.dropped += 1
            if conn.dropped % 50 == 1:
                log_event(LOG, "ws_rate_limited", player_id=pid, dropped=conn.dropped)
            if conn.dropped > MAX_DROPPED:
                conn.request_close(POLICY)
                return
            continue
        msg = parse_client(raw)
        if isinstance(msg, ValidationError):
            log_invalid(msg)
            runtime.hub.send_on(conn, ErrorMsg(t="ERROR", code=ErrorCode.INVALID_MESSAGE))
            continue
        if runtime.hub.current(pid) is not conn:
            return  # superseded meanwhile
        match msg:
            case Ping(c=echo):
                runtime.hub.send_on(conn, Pong(t="PONG", c=echo, s=precise))
            case Hello():
                pass
            case AnswerSubmit():
                runtime.dispatch(c.SubmitIn(pid, msg), at=now)
            case AnswerDraft():
                runtime.dispatch(c.DraftIn(pid, msg), at=now)
            case AudioStatus():
                runtime.dispatch(c.AudioStatusIn(pid, msg), at=now)
            case PlaybackReport():
                runtime.dispatch(c.PlaybackReportIn(pid, msg), at=now)
            case _:
                runtime.dispatch(c.HostIn(pid, msg), at=now)  # type: ignore[arg-type]
