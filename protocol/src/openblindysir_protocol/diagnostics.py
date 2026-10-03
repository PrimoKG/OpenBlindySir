"""Host diagnostics (``GET /api/host/diagnostics``, spec §21).

Never exposes track ids, relative paths, file names or tags, even in MC Mode: the JSON is
meant to be attached to a public issue.
"""

from typing import Annotated

from pydantic import Field, StringConstraints

from openblindysir_protocol.base import JobId, OutboundModel, PlayerId, RoundId
from openblindysir_protocol.compatibility import Compatibility
from openblindysir_protocol.enums import (
    AssetRole,
    AssetState,
    AudioErrorCode,
    AudioState,
    BrowserFamily,
    ConnectionState,
    JobStage,
    RoundState,
)
from openblindysir_protocol.views import BridgeDetail, BridgeStatus


class DiagPlayer(OutboundModel):
    player_id: PlayerId
    nickname: str
    connection: ConnectionState
    audio_state: AudioState  # LOCKED <=> the client's AudioContext is not "running"
    audio_error: AudioErrorCode | None
    rtt_min_ms: float | None
    offset_ms: float | None
    epsilon_ms: float | None
    last_late_ms: float | None
    last_est_error_ms: float | None
    out_latency_ms: float | None
    client_version: str | None
    browser_family: BrowserFamily | None


class DiagJob(OutboundModel):
    job_id: JobId
    asset_state: AssetState
    stage: JobStage | None
    age_ms: int
    bridge_id: str | None = None


class DiagCacheAsset(OutboundModel):
    asset_ref: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8}$")]
    role: AssetRole | None
    state: AssetState
    bytes: int


class DiagUnvalidated(OutboundModel):
    player_id: PlayerId
    draft_last_changed_ms: int | None  # relative to official_start_at


class DiagRound(OutboundModel):
    """Only rounds whose answers were closed (REVIEW, REVEALED, CANCELLED after REVIEW)."""

    round_id: RoundId
    number: int
    state: RoundState
    unvalidated: list[DiagUnvalidated]
    playback_p50_ms: float | None
    playback_p90_ms: float | None
    playback_max_ms: float | None


class DiagnosticsResponse(OutboundModel):
    server_version: str
    protocol: int
    uptime_s: int
    loop_lag_p99_ms: float
    players: list[DiagPlayer]
    bridge: BridgeStatus
    jobs: list[DiagJob]
    cache_used_bytes: int
    cache_cap_bytes: int
    cache: list[DiagCacheAsset]
    rounds: list[DiagRound]
    compatibility: Compatibility | None = None
    bridges: list[BridgeDetail] = Field(default_factory=list)
    persistence_status: str = "disabled"
    history_count: int = 0
    history_bytes: int = 0
