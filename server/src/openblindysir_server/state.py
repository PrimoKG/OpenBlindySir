"""Per-application state shared by the routes (no module-level state)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.config import Settings
from openblindysir_server.logging import get, log_event
from openblindysir_server.ratelimit import ConnectionCounter, SlidingWindowLimiter

if TYPE_CHECKING:
    from openblindysir_server.runtime import Runtime

LOG = get("http")


@dataclass(eq=False)
class AppState:
    settings: Settings
    runtime: Runtime
    join_limiter: SlidingWindowLimiter
    host_limiter: SlidingWindowLimiter
    ws_counter: ConnectionCounter
    started_mono: int
    lag: Any  # diagnostics.LoopLagMonitor (typed loosely to avoid an import cycle)
    recovery_limiter: SlidingWindowLimiter = field(
        default_factory=lambda: SlidingWindowLimiter(5, 60)
    )
    bridge_auth_limiter: SlidingWindowLimiter = field(
        default_factory=lambda: SlidingWindowLimiter(10, 60)
    )
    bridge_counter: ConnectionCounter = field(default_factory=lambda: ConnectionCounter(12))
    join_activity_limiter: SlidingWindowLimiter = field(
        default_factory=lambda: SlidingWindowLimiter(60, 600)
    )


def app_state(conn: HTTPConnection) -> AppState:
    return conn.app.state.obs


def client_ip(conn: HTTPConnection) -> str:
    return conn.client.host if conn.client else "-"


def invalid_body(exc: ValidationError, kind: str) -> JSONResponse:
    """Log only the field path and error type of untrusted input, never its value."""
    errors = exc.errors(include_url=False, include_input=False, include_context=False)
    first = errors[0] if errors else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    log_event(
        LOG, "http_invalid_body", kind=kind, loc=loc, type=first.get("type", "?"), count=len(errors)
    )
    return JSONResponse({"error": ErrorCode.INVALID_MESSAGE.value}, status_code=400)
