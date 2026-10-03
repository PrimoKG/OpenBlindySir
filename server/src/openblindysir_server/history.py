"""Host-only history consultation, exports and explicit durable deletion."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.http import ConfirmRequest
from openblindysir_protocol.views import HistoryItem, HistoryResponse
from openblindysir_server.game.history import MAX_BYTES, MAX_GAMES, RETENTION_DAYS, record_bytes
from openblindysir_server.library.management import host_access
from openblindysir_server.security import error, read_json_body
from openblindysir_server.state import app_state

router = APIRouter()


@router.get("/api/host/history")
async def history(request: Request) -> Response:
    state = app_state(request)
    denied = host_access(request, state)
    if denied is not None:
        return denied
    records = state.runtime.engine.state.archives
    response = HistoryResponse(
        items=[
            HistoryItem(
                game_id=row["game_id"],
                finished_at=row["finished_at"],
                rounds_played=row["results"]["rounds_played"],
                participants=len(row["players"]),
            )
            for row in reversed(records)
        ],
        retained_bytes=sum(record_bytes(row) for row in records),
        max_games=MAX_GAMES,
        max_bytes=MAX_BYTES,
        retention_days=RETENTION_DAYS,
        durable=state.runtime.snapshots is not None
        and state.runtime.engine.state.persistence_status == "ready",
    )
    return JSONResponse(response.model_dump(mode="json"))


@router.get("/api/host/history/{game_id}")
async def history_record(request: Request, game_id: str) -> Response:
    state = app_state(request)
    denied = host_access(request, state)
    if denied is not None:
        return denied
    record = next((r for r in state.runtime.engine.state.archives if r["game_id"] == game_id), None)
    if record is None:
        return error(404, ErrorCode.NOT_FOUND)
    return JSONResponse(record)


@router.delete("/api/host/history")
@router.delete("/api/host/history/{game_id}")
async def delete_history(request: Request, game_id: str | None = None) -> Response:
    state = app_state(request)
    denied = host_access(request, state, mutation=True)
    if denied is not None:
        return denied
    raw = await read_json_body(request, 128)
    if isinstance(raw, Response):
        return raw
    try:
        confirmed = ConfirmRequest.model_validate_json(raw).confirm
    except ValidationError:
        return error(400, ErrorCode.INVALID_ARGS)
    if not confirmed:
        return error(400, ErrorCode.INVALID_ARGS)
    denied = host_access(request, state, mutation=True)
    if denied is not None:
        return denied
    runtime = state.runtime
    previous = runtime.engine.state.archives
    if game_id is not None and not any(row["game_id"] == game_id for row in previous):
        return error(404, ErrorCode.NOT_FOUND)
    runtime.engine.state.archives = [
        row for row in previous if game_id is not None and row["game_id"] != game_id
    ]
    try:
        if runtime.snapshots is not None:
            runtime.snapshots.save(
                runtime.engine, runtime.sessions, runtime.clock.now(), purge_previous=True
            )
    except (OSError, ValueError):
        runtime.engine.state.archives = previous
        runtime.engine.state.persistence_status = "failed"
        runtime.hub.mark_dirty()
        return error(503, ErrorCode.INVALID_STATE)
    runtime.engine.state.persistence_status = "ready" if runtime.snapshots else "disabled"
    runtime.engine.state.version += 1
    runtime.hub.mark_dirty()
    return JSONResponse({"ok": True})
