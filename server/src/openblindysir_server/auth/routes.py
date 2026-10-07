"""Session routes (spec §8.1): join, who-am-I, host elevation, leave."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.http import (
    HostElevateRequest,
    HostElevateResponse,
    JoinRequest,
    JoinResponse,
    OkResponse,
    RecoveryCode,
    RecoveryRequest,
    SessionResponse,
)
from openblindysir_protocol.text import normalize_nickname
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_server import __version__
from openblindysir_server.auth.cookies import clear_session_cookie, read_token, set_session_cookie
from openblindysir_server.auth.sessions import verify_password
from openblindysir_server.game import commands as c
from openblindysir_server.logging import get, log_event
from openblindysir_server.security import check_origin, error, read_json_body, truncate_ip
from openblindysir_server.state import AppState, app_state, client_ip, invalid_body

router = APIRouter()
LOG = get("auth")


def _session_response(state: AppState, player_id: str) -> SessionResponse:
    p = state.runtime.engine.state.players[player_id]
    return SessionResponse(
        player_id=p.id,
        nickname=p.nickname,
        role=p.role,
        host_mode=p.host_mode if p.role.value == "host" else None,
        protocol=PROTOCOL_VERSION,
        server_version=__version__,
        epoch=state.runtime.engine.state.epoch,
    )


def _json(model: object, status: int = 200) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json"), status_code=status)  # type: ignore[attr-defined]


def persistence_error() -> JSONResponse:
    # HTTP-only access error: no WebSocket protocol change.
    return JSONResponse({"error": "persistence_failed"}, status_code=503)


def current_player(request: Request, state: AppState) -> str | None:
    now = state.runtime.clock.now().mono_ms
    pid = state.runtime.sessions.resolve(read_token(request, state.settings), now)
    if pid is None or not state.runtime.engine.player_exists(pid):
        return None
    return pid


@router.post("/api/session/join")
async def join(request: Request) -> Response:
    state = app_state(request)
    if not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    ip = client_ip(request)
    now = state.runtime.clock.now().mono_ms
    if state.join_limiter.blocked(ip, now):  # counts failed password attempts only
        return error(429, ErrorCode.RATE_LIMITED)
    if not state.join_activity_limiter.allow(ip, now):
        return error(429, ErrorCode.RATE_LIMITED)
    body = await read_json_body(request)
    if isinstance(body, Response):
        return body
    try:
        payload = JoinRequest.model_validate_json(body)
    except ValidationError as exc:
        return invalid_body(exc, "join")
    now = state.runtime.clock.now().mono_ms
    if state.join_limiter.blocked(ip, now):
        return error(429, ErrorCode.RATE_LIMITED)
    if current_player(request, state) is not None:
        return error(409, ErrorCode.ALREADY_JOINED)
    if not verify_password(payload.password, state.settings.blind_password):
        state.join_limiter.record(ip, now)
        log_event(LOG, "login_failed", kind="join", ip=truncate_ip(ip))
        return error(401, ErrorCode.BAD_PASSWORD)
    try:
        normalize_nickname(payload.nickname)
    except ValueError:
        return error(422, ErrorCode.NICKNAME_INVALID)
    outcome = state.runtime.dispatch(c.Join(payload.nickname))
    if outcome.error is ErrorCode.NICKNAME_INVALID:
        return error(422, ErrorCode.NICKNAME_INVALID)
    if outcome.error is not None:
        return error(409, outcome.error)
    player_id = outcome.value
    assert isinstance(player_id, str)
    token = state.runtime.sessions.issue(player_id, now)
    state.runtime.save_snapshot()
    p = state.runtime.engine.state.players[player_id]
    response = _json(JoinResponse(player_id=p.id, nickname=p.nickname, role=p.role))
    set_session_cookie(response, token, state.settings)
    return response


@router.post("/api/session/recovery-code")
async def recovery_code(request: Request) -> Response:
    state = app_state(request)
    if not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    pid = current_player(request, state)
    if pid is None:
        return error(401, ErrorCode.UNAUTHENTICATED)
    if not state.recovery_limiter.allow(pid, state.runtime.clock.now().mono_ms):
        return error(429, ErrorCode.RATE_LIMITED)
    candidate = state.runtime.session_candidate()
    code = candidate.recovery_code(pid)
    if not state.runtime.commit_sessions(candidate):
        return persistence_error()
    return _json(RecoveryCode(code=code))


@router.post("/api/session/recover")
async def recover(request: Request) -> Response:
    state = app_state(request)
    runtime = state.runtime
    if not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    now = runtime.clock.now().mono_ms
    ip = client_ip(request)
    if state.join_limiter.blocked(ip, now):
        return error(429, ErrorCode.RATE_LIMITED)
    state.join_limiter.record(ip, now)
    body = await read_json_body(request)
    if isinstance(body, Response):
        return body
    try:
        payload = RecoveryRequest.model_validate_json(body)
    except ValidationError as exc:
        return invalid_body(exc, "recover")
    if current_player(request, state) is not None:
        return error(409, ErrorCode.ALREADY_JOINED)
    if not verify_password(payload.password, state.settings.blind_password):
        return error(401, ErrorCode.RECOVERY_INVALID)
    candidate = runtime.session_candidate()
    pid = candidate.recover(payload.code)
    if pid is None or not runtime.engine.player_exists(pid):
        return error(401, ErrorCode.RECOVERY_INVALID)
    token = runtime.transfer_identity(pid, candidate, runtime.clock.now().mono_ms)
    if token is None:
        return persistence_error()
    response = _json(_session_response(state, pid))
    set_session_cookie(response, token, state.settings)
    return response


@router.get("/api/session")
async def whoami(request: Request) -> Response:
    state = app_state(request)
    player_id = current_player(request, state)
    if player_id is None:
        return error(401, ErrorCode.UNAUTHENTICATED)
    response = _json(_session_response(state, player_id))
    token = read_token(request, state.settings)
    assert token is not None
    set_session_cookie(response, token, state.settings)  # refreshed Max-Age, same token
    return response


@router.post("/api/session/host")
async def elevate(request: Request) -> Response:
    state = app_state(request)
    if not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    player_id = current_player(request, state)
    if player_id is None:
        return error(401, ErrorCode.UNAUTHENTICATED)
    ip = client_ip(request)
    now = state.runtime.clock.now().mono_ms
    if state.host_limiter.blocked(ip, now):  # counts failed password attempts only
        return error(429, ErrorCode.RATE_LIMITED)
    body = await read_json_body(request)
    if isinstance(body, Response):
        return body
    try:
        payload = HostElevateRequest.model_validate_json(body)
    except ValidationError as exc:
        return invalid_body(exc, "host")
    if current_player(request, state) != player_id:
        return error(401, ErrorCode.UNAUTHENTICATED)
    now = state.runtime.clock.now().mono_ms
    if state.host_limiter.blocked(ip, now):
        return error(429, ErrorCode.RATE_LIMITED)
    if not verify_password(payload.host_password, state.settings.host_password):
        state.host_limiter.record(ip, now)
        log_event(LOG, "login_failed", kind="host", ip=truncate_ip(ip))
        return error(401, ErrorCode.BAD_PASSWORD)
    state.runtime.dispatch(c.ElevateHost(player_id))
    p = state.runtime.engine.state.players[player_id]
    response = _json(HostElevateResponse(role="host", host_mode=p.host_mode))
    token = read_token(request, state.settings)
    assert token is not None
    set_session_cookie(response, token, state.settings)
    return response


@router.post("/api/session/leave")
async def leave(request: Request) -> Response:
    state = app_state(request)
    if not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    player_id = current_player(request, state)
    if player_id is None:
        return error(401, ErrorCode.UNAUTHENTICATED)
    body = await read_json_body(request)
    if isinstance(body, Response):
        return body
    if current_player(request, state) != player_id:
        return error(401, ErrorCode.UNAUTHENTICATED)
    state.runtime.dispatch(c.Leave(player_id))
    response = _json(OkResponse(ok=True))
    clear_session_cookie(response, state.settings)
    return response
