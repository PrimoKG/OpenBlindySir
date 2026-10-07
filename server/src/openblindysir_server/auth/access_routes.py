"""QR joins and shared session codes; existing identities require host approval."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, StringConstraints, ValidationError

from openblindysir_protocol.base import InboundModel
from openblindysir_protocol.enums import ConnectionState
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.text import nickname_key, normalize_nickname
from openblindysir_server.auth.cookies import set_session_cookie
from openblindysir_server.auth.routes import (
    _json,
    _session_response,
    current_player,
    persistence_error,
)
from openblindysir_server.auth.sessions import hash_token
from openblindysir_server.game import commands as c
from openblindysir_server.library.management import host_access
from openblindysir_server.security import check_origin, error, read_json_body
from openblindysir_server.state import AppState, app_state, client_ip

router = APIRouter()
Text = Annotated[str, StringConstraints(max_length=256)]


class AccessJoin(InboundModel):
    nickname: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    code: Text = ""
    invitation: Text = ""


class AccessPoll(InboundModel):
    request_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
    token: Text


class AccessRotate(InboundModel):
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z2-9]{6,16}$")] | None = None


class AccessDecision(InboundModel):
    request_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
    approve: Annotated[bool, Field(strict=True)]


@router.get("/api/session/access-code")
async def shared_code(request: Request) -> Response:
    state = app_state(request)
    pid = current_player(request, state)
    if pid is None:
        return error(401, ErrorCode.UNAUTHENTICATED)
    if not state.access_read_limiter.allow(pid, state.runtime.clock.now().mono_ms):
        return error(429, ErrorCode.RATE_LIMITED)
    if not ensure_access(state):
        return persistence_error()
    return JSONResponse({"code": state.runtime.sessions.access.code})


@router.get("/api/host/session/access")
async def host_access_details(request: Request) -> Response:
    state = app_state(request)
    denied = host_access(request, state, library=False)
    if denied is not None:
        return denied
    if not ensure_access(state):
        return persistence_error()
    access = state.runtime.sessions.access
    access.prune(state.runtime.clock.now().mono_ms)
    players = state.runtime.engine.state.players
    return JSONResponse(
        {
            "code": access.code,
            "invitation": access.invitation,
            "requests": [
                {
                    "request_id": key,
                    "nickname": players[claim.player_id].nickname,
                    "reference": claim.reference,
                }
                for key, claim in access.claims.items()
                if claim.player_id in players and not claim.approved
            ],
        }
    )


@router.post("/api/host/session/access")
async def rotate_access(request: Request) -> Response:
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
        payload = AccessRotate.model_validate_json(raw)
    except ValidationError:
        return error(400, ErrorCode.INVALID_ARGS)
    candidate = state.runtime.session_candidate()
    candidate.access.rotate(payload.code)
    if not state.runtime.commit_sessions(candidate):
        return persistence_error()
    return JSONResponse({"ok": True})


@router.post("/api/session/access")
async def join_access(request: Request) -> Response:
    state = app_state(request)
    if not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    now, ip = state.runtime.clock.now().mono_ms, client_ip(request)
    if state.join_limiter.blocked(ip, now) or not state.join_activity_limiter.allow(ip, now):
        return error(429, ErrorCode.RATE_LIMITED)
    raw = await read_json_body(request)
    if isinstance(raw, Response):
        return raw
    try:
        payload = AccessJoin.model_validate_json(raw)
        normalize_nickname(payload.nickname)
    except (ValidationError, ValueError):
        return error(400, ErrorCode.INVALID_ARGS)
    now = state.runtime.clock.now().mono_ms
    if state.join_limiter.blocked(ip, now):
        return error(429, ErrorCode.RATE_LIMITED)
    if current_player(request, state) is not None:
        return error(409, ErrorCode.ALREADY_JOINED)
    access = state.runtime.sessions.access
    if not access.valid(payload.code, payload.invitation):
        state.join_limiter.record(ip, now)
        return error(401, ErrorCode.RECOVERY_INVALID)
    existing = next(
        (
            p
            for p in state.runtime.engine.state.players.values()
            if p.connection is not ConnectionState.REMOVED
            and nickname_key(p.nickname) == nickname_key(payload.nickname)
        ),
        None,
    )
    if existing:
        try:
            key, token = access.claim(
                existing.id, now, hash_token(ip), capacity=max(32, 2 * state.settings.max_players)
            )
        except ValueError:
            return error(429, ErrorCode.RATE_LIMITED)
        return JSONResponse(
            {
                "status": "waiting",
                "request_id": key,
                "token": token,
                "reference": access.claims[key].reference,
            },
            status_code=202,
        )
    outcome = state.runtime.dispatch(c.Join(payload.nickname))
    if outcome.error:
        return error(409, outcome.error)
    assert isinstance(outcome.value, str)
    token = state.runtime.sessions.issue(outcome.value, now)
    state.runtime.save_snapshot()
    response = _json(_session_response(state, outcome.value))
    set_session_cookie(response, token, state.settings)
    return response


@router.post("/api/host/session/access/decide")
async def decide_claim(request: Request) -> Response:
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
        payload = AccessDecision.model_validate_json(raw)
    except ValidationError:
        return error(400, ErrorCode.INVALID_ARGS)
    access = state.runtime.sessions.access
    access.prune(state.runtime.clock.now().mono_ms)
    claim = access.claims.get(payload.request_id)
    if not claim:
        return error(404, ErrorCode.NOT_FOUND)
    if payload.approve:
        claim.approved = True
    else:
        del access.claims[payload.request_id]
    return JSONResponse({"ok": True})


@router.post("/api/session/access/poll")
async def poll_claim(request: Request) -> Response:
    state = app_state(request)
    if not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    raw = await read_json_body(request)
    if isinstance(raw, Response):
        return raw
    try:
        payload = AccessPoll.model_validate_json(raw)
    except ValidationError:
        return error(400, ErrorCode.INVALID_ARGS)
    now = state.runtime.clock.now().mono_ms
    if current_player(request, state) is not None:
        return error(409, ErrorCode.ALREADY_JOINED)
    access = state.runtime.sessions.access
    access.prune(now)
    claim = access.claims.get(payload.request_id)
    if not claim or not secrets_equal(claim.token_hash, hash_token(payload.token)):
        return error(401, ErrorCode.RECOVERY_INVALID)
    if not state.access_poll_limiter.allow(payload.request_id, now):
        return error(429, ErrorCode.RATE_LIMITED)
    if not claim.approved:
        return JSONResponse({"status": "waiting"}, status_code=202)
    pid = claim.player_id
    if not state.runtime.engine.player_exists(pid):
        return error(401, ErrorCode.RECOVERY_INVALID)
    candidate = state.runtime.session_candidate()
    candidate.access.claims = {
        key: item for key, item in candidate.access.claims.items() if item.player_id != pid
    }
    token = state.runtime.transfer_identity(pid, candidate, now)
    if token is None:
        return persistence_error()
    response = _json(_session_response(state, pid))
    set_session_cookie(response, token, state.settings)
    return response


def ensure_access(state: AppState) -> bool:
    if state.runtime.sessions.access.code:
        return True
    candidate = state.runtime.session_candidate()
    candidate.access.ensure()
    return state.runtime.commit_sessions(candidate)


def secrets_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
