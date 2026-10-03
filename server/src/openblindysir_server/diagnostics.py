"""Host diagnostics (``GET /api/host/diagnostics``, spec §21) and the event-loop lag monitor.

Never exposes track ids, paths, file names, tags or secrets. Host diagnostics can
contain nicknames and source names: anonymize them before sharing.
"""

import asyncio
import statistics
from collections import deque

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from openblindysir_protocol.compatibility import Compatibility
from openblindysir_protocol.diagnostics import (
    DiagCacheAsset,
    DiagJob,
    DiagnosticsResponse,
    DiagPlayer,
    DiagRound,
    DiagUnvalidated,
)
from openblindysir_protocol.enums import AnswerStatus, ConnectionState, GamePhase, HostMode
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_server import __version__
from openblindysir_server.auth.cookies import read_token
from openblindysir_server.game.history import record_bytes
from openblindysir_server.game.state import IN_FLIGHT_ASSET_STATES
from openblindysir_server.game.views import bridge_details, bridge_status
from openblindysir_server.logging import get, log_event
from openblindysir_server.security import error
from openblindysir_server.state import AppState, app_state

router = APIRouter()
LOG = get("diagnostics")
LAG_WARN_MS = 50


class LoopLagMonitor:
    """Measures event-loop lag: a blocked loop skews PONG and answer timestamps (spec §27)."""

    def __init__(self, interval_s: float = 0.5) -> None:
        self.interval_s = interval_s
        self.samples: deque[float] = deque(maxlen=240)

    @property
    def p99_ms(self) -> float:
        if len(self.samples) < 2:
            return max(self.samples, default=0.0)
        return statistics.quantiles(self.samples, n=100)[98]

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            start = loop.time()
            await asyncio.sleep(self.interval_s)
            lag_ms = max(0.0, (loop.time() - start - self.interval_s) * 1000)
            self.samples.append(lag_ms)
            if lag_ms > LAG_WARN_MS:
                log_event(LOG, "loop_lag", ms=round(lag_ms))


def _percentile(values: list[float], q: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100)[q - 1]


def build(state: AppState, *, private_sources: bool = True) -> DiagnosticsResponse:
    runtime = state.runtime
    s = runtime.engine.state
    now = runtime.clock.now().mono_ms
    families = {conn.player_id: conn.browser_family for conn in runtime.hub.connections()}
    players = [
        DiagPlayer(
            player_id=p.id,
            nickname=p.nickname,
            connection=p.connection,
            audio_state=p.audio_state,
            audio_error=p.audio_error,
            rtt_min_ms=p.rtt_min_ms,
            offset_ms=p.clock_offset_ms,
            epsilon_ms=None if p.rtt_min_ms is None else p.rtt_min_ms / 2,
            last_late_ms=p.last_report.late_ms if p.last_report else None,
            last_est_error_ms=p.last_report.est_error_ms if p.last_report else None,
            out_latency_ms=p.last_report.out_latency_ms if p.last_report else None,
            client_version=p.client_version,
            browser_family=families.get(p.id),
        )
        for p in s.players.values()
        if p.connection is not ConnectionState.REMOVED
    ]
    jobs = [
        DiagJob(
            job_id=a.job_id,
            asset_state=a.state,
            stage=a.stage,
            age_ms=now - a.requested_at,
            bridge_id=a.track_ref.bridge_id,
        )
        for a in s.assets.values()
        if a.state in IN_FLIGHT_ASSET_STATES
    ]
    roles = runtime.engine.retained_assets()
    cache = [
        DiagCacheAsset(
            asset_ref=asset_id[2:10],
            role=roles.get(asset_id),
            state=s.assets[asset_id].state,
            bytes=size,
        )
        for asset_id, size in runtime.cache.items()
        if asset_id in s.assets
    ]
    rounds = []
    for r in s.game.rounds:
        if r.closed_at is None:
            continue
        start = r.official_start_at or 0
        unvalidated = [
            DiagUnvalidated(
                player_id=a.player_id,
                draft_last_changed_ms=(
                    None if a.draft_last_changed_at is None else a.draft_last_changed_at - start
                ),
            )
            for a in r.answers.values()
            if a.status is AnswerStatus.CAPTURED
            or (a.status is AnswerStatus.NONE and a.draft_last_changed_at is not None)
        ]
        rounds.append(
            DiagRound(
                round_id=r.id,
                number=r.number,
                state=r.state,
                unvalidated=unvalidated,
                playback_p50_ms=_percentile(r.playback_late_ms, 50),
                playback_p90_ms=_percentile(r.playback_late_ms, 90),
                playback_max_ms=max(r.playback_late_ms, default=None),
            )
        )
    return DiagnosticsResponse(
        server_version=__version__,
        protocol=PROTOCOL_VERSION,
        uptime_s=(now - state.started_mono) // 1000,
        loop_lag_p99_ms=round(state.lag.p99_ms, 1),
        players=players,
        bridge=bridge_status(s)
        if private_sources
        else bridge_status(s).model_copy(update={"name": None}),
        jobs=jobs,
        cache_used_bytes=runtime.cache.used_bytes,
        cache_cap_bytes=runtime.cache.cap_bytes,
        cache=cache,
        rounds=rounds,
        compatibility=Compatibility(server_version=__version__),
        bridges=bridge_details(s) if private_sources else [],
        persistence_status=s.persistence_status,
        history_count=len(s.archives),
        history_bytes=sum(record_bytes(row) for row in s.archives),
    )


@router.get("/api/host/diagnostics")
async def diagnostics(request: Request) -> Response:
    state = app_state(request)
    runtime = state.runtime
    pid = runtime.sessions.resolve(read_token(request, state.settings), runtime.clock.now().mono_ms)
    if pid is None or not runtime.engine.player_exists(pid):
        return error(401, ErrorCode.UNAUTHENTICATED)
    if not runtime.engine.is_host(pid):
        return error(403, ErrorCode.NOT_HOST)
    s = runtime.engine.state
    private_sources = (
        s.game.phase is not GamePhase.IN_GAME or s.players[pid].host_mode is HostMode.MC
    )
    return JSONResponse(build(state, private_sources=private_sources).model_dump(mode="json"))
