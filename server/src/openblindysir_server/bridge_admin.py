"""The host can revoke a Bridge; secret creation/rotation is a local operator command."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.http import ConfirmRequest
from openblindysir_server.auth.bridges import valid_id
from openblindysir_server.library.management import host_access
from openblindysir_server.security import error, read_json_body
from openblindysir_server.state import app_state

router = APIRouter()


@router.post("/api/host/bridges/{bridge_id}/revoke")
async def revoke(request: Request, bridge_id: str) -> Response:
    state = app_state(request)
    denied = host_access(request, state, mutation=True, library=False)
    if denied is not None:
        return denied
    raw = await read_json_body(request, 128)
    if isinstance(raw, Response):
        return raw
    try:
        valid_id(bridge_id)
        confirmed = ConfirmRequest.model_validate_json(raw).confirm
    except (ValueError, ValidationError):
        return error(400, ErrorCode.INVALID_ARGS)
    if not confirmed:
        return error(400, ErrorCode.INVALID_ARGS)
    denied = host_access(request, state, mutation=True, library=False)
    if denied is not None:
        return denied
    try:
        if not state.runtime.credentials.revoke(bridge_id):
            return error(404, ErrorCode.NOT_FOUND)
    except (OSError, ValueError):
        return error(503, ErrorCode.INVALID_STATE)
    state.runtime.refresh_bridge_credentials()
    return JSONResponse({"ok": True})
