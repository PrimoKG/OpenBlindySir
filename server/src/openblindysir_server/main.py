"""Application factory. No module-level state: two apps in one process are independent."""

import asyncio
import contextlib
import random
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from openblindysir_protocol.compatibility import Compatibility
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.http import HealthResponse
from openblindysir_server import __version__, bridge_admin, history
from openblindysir_server.audio import review as review_routes
from openblindysir_server.audio import routes as audio_routes
from openblindysir_server.audio.cache import AudioCache
from openblindysir_server.auth import routes as auth_routes
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.config import Settings, to_core_config
from openblindysir_server.diagnostics import LoopLagMonitor
from openblindysir_server.diagnostics import router as diagnostics_router
from openblindysir_server.game import Clock, GameEngine, IdFactory, MonotonicClock, SecretIds
from openblindysir_server.game import commands as c
from openblindysir_server.library import management as library_management
from openblindysir_server.library import routes as library_routes
from openblindysir_server.logging import get, log_event
from openblindysir_server.ratelimit import ConnectionCounter, SlidingWindowLimiter
from openblindysir_server.runtime import Runtime
from openblindysir_server.security import SecurityHeadersMiddleware, error
from openblindysir_server.state import AppState
from openblindysir_server.ws import bridge_endpoint, player_endpoint
from openblindysir_server.ws.bridge_link import BridgeLink
from openblindysir_server.ws.hub import PlayerHub

LOG = get("server")
SWEEP_INTERVAL_S = 5
OFFLINE_AFTER_MS = 20_000
MAX_WS_PER_IP = 20


def create_app(
    settings: Settings,
    *,
    clock: Clock | None = None,
    ids: IdFactory | None = None,
    rng: random.Random | None = None,
    background_tasks: bool = True,
) -> FastAPI:
    clock = clock or MonotonicClock()
    engine = GameEngine(
        to_core_config(settings),
        ids=ids or SecretIds(),
        rng=rng or random.SystemRandom(),
        started_at=clock.now(),
    )
    holder: dict[str, Runtime] = {}

    def view_json(player_id: str) -> str | None:
        return holder["runtime"].view_json(player_id)

    runtime = Runtime(
        settings=settings,
        engine=engine,
        clock=clock,
        hub=PlayerHub(view_json),
        bridge=BridgeLink(),
        cache=AudioCache(settings.audio_cache_mb * 1024 * 1024, settings.max_clip_mb * 1024 * 1024),
        sessions=SessionRegistry(settings.session_idle_ttl_h * 3600 * 1000),
    )
    holder["runtime"] = runtime
    lag = LoopLagMonitor()
    state = AppState(
        settings=settings,
        runtime=runtime,
        join_limiter=SlidingWindowLimiter(5, 60),
        host_limiter=SlidingWindowLimiter(3, 20),
        ws_counter=ConnectionCounter(MAX_WS_PER_IP),
        started_mono=clock.now().mono_ms,
        lag=lag,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        tasks: list[asyncio.Task[None]] = []
        if background_tasks:
            tasks.append(asyncio.create_task(lag.run()))
            tasks.append(asyncio.create_task(_sweeper(runtime)))
        log_event(LOG, "session_started", dev_mode=settings.dev_mode)
        if settings.dev_mode:
            log_event(LOG, "dev_mode_enabled")
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            runtime.shutdown()

    app = FastAPI(
        title="OpenBlindySir", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.obs = state

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        del request, exc  # never echo the input (the default handler does)
        return JSONResponse({"error": ErrorCode.INVALID_MESSAGE.value}, status_code=400)

    @app.get("/healthz")
    async def healthz() -> Response:
        bridge = None
        if settings.dev_mode:
            from openblindysir_server.game.views import bridge_status  # noqa: PLC0415

            bridge = bridge_status(engine.state).state
        return JSONResponse(HealthResponse(status="ok", bridge=bridge).model_dump(mode="json"))

    for router in (
        auth_routes.router,
        player_endpoint.router,
        bridge_endpoint.router,
        library_routes.router,
        library_management.router,
        audio_routes.router,
        review_routes.router,
        diagnostics_router,
        history.router,
        bridge_admin.router,
    ):
        app.include_router(router)
    _mount_spa(app, settings.static_dir)

    @app.get("/api/compatibility")
    async def compatibility() -> Response:
        return JSONResponse(Compatibility(server_version=__version__).model_dump(mode="json"))

    app.add_middleware(SecurityHeadersMiddleware, hsts=not settings.dev_mode)
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=list(settings.trusted_proxies))
    return app


def _mount_spa(app: FastAPI, static_dir: Path | None) -> None:
    """``/`` and ``/host`` serve index.html; ``/assets/*`` serves hashed files."""

    @app.get("/")
    @app.get("/host")
    async def index() -> Response:
        if static_dir is None or not (static_dir / "index.html").is_file():
            return error(404, ErrorCode.NOT_FOUND)
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/assets/{name}")
    async def asset(name: str) -> Response:
        if static_dir is None or "/" in name or "\\" in name or name.startswith("."):
            return error(404, ErrorCode.NOT_FOUND)
        path = (static_dir / "assets" / name).resolve()
        root = (static_dir / "assets").resolve()
        if path.parent != root or not path.is_file():
            return error(404, ErrorCode.NOT_FOUND)
        return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


def sweep_once(runtime: Runtime) -> list[str]:
    """Heartbeat (spec §7.4): a connection silent for about 20 s goes OFFLINE.

    The connection is removed from the hub here, so the endpoint will not report the
    disconnection itself: the sweeper dispatches it. Idle sessions expire too.
    """
    runtime.refresh_bridge_credentials()
    now = runtime.clock.now().mono_ms
    swept: list[str] = []
    for conn in runtime.hub.connections():
        if now - conn.last_rx_mono > OFFLINE_AFTER_MS:
            runtime.hub.close(conn.player_id, 1001)
            runtime.dispatch(c.Disconnected(conn.player_id))
            log_event(LOG, "player_heartbeat_lost", player_id=conn.player_id)
            swept.append(conn.player_id)
    runtime.sessions.expire_idle(now)
    runtime.save_snapshot()
    return swept


async def _sweeper(runtime: Runtime) -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_S)
        sweep_once(runtime)
