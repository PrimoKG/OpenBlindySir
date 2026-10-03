"""Per-recipient views sent in ``STATE`` (spec §6.8, §8.2).

There is one root model per audience (``PlayerView``, ``HostPlayerModeView``,
``HostMcView``) and audience-specific round unions, so a datum that an audience must not
see has no field to live in. Names such as ``relpath``, ``track_id`` or
``draft_last_changed_at`` exist in no view model.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from openblindysir_protocol.base import AssetId, GameId, OutboundModel, PlayerId, PlayId, RoundId
from openblindysir_protocol.enums import (
    AnswerStatus,
    AssetState,
    AudioErrorCode,
    AudioState,
    BridgeState,
    ConnectionState,
    GamePhase,
    HostMode,
    HostWarning,
    Role,
)
from openblindysir_protocol.errors import StartBlocker
from openblindysir_protocol.settings import GameSettings, ServerLimits

# --- common sub-models -------------------------------------------------------------------


class SessionInfo(OutboundModel):
    epoch: str  # 16 hex; changes on end_session and on process restart
    protocol: int
    server_version: str
    recovered: bool = False
    persistence_status: str = "disabled"


class Me(OutboundModel):
    player_id: PlayerId
    nickname: str
    role: Role
    host_mode: HostMode | None  # None iff role == player
    participant: bool  # answers rounds (False for an MC host)


class ViewPlayer(OutboundModel):
    """Public player entry: NO answer-related field, ever (spec patch 2)."""

    id: PlayerId
    nickname: str
    online: bool
    is_host: bool
    is_me: bool
    spectator: bool = False
    team: str | None = None


class TeamStanding(OutboundModel):
    team: str
    score: int
    rank: int
    members: list[PlayerId]


class GameRules(OutboundModel):
    custom_points: int = 1
    answer_mode: str
    title_points: int
    artist_points: int
    instructions: str
    captured_policy: str


class PauseInfo(OutboundModel):
    paused_at: int
    remaining_ms: int
    clip_offset_s: float | None
    resume_at: int | None = None


class StandingRow(OutboundModel):
    player_id: PlayerId
    score: int  # sum of the active events of the current game
    rank: int  # competition ranking 1, 1, 3


class GameInfo(OutboundModel):
    game_id: GameId
    rounds_total: int
    round_number: int | None
    clip_seconds: int


class AudioRef(OutboundModel):
    asset_id: AssetId
    url: str  # "/api/audio/{asset_id}"
    duration_ms: int


class AudioSlots(OutboundModel):
    current: AudioRef | None
    next: AudioRef | None  # only while the current round is REVIEW or REVEALED (spec §7.3)


class PlayInfo(OutboundModel):
    """Same content as PLAY, for late joiners and reconnections (spec §8.2)."""

    play_id: PlayId
    asset_id: AssetId
    start_at: int
    clip_offset: float


class Progress(OutboundModel):
    """Anonymous counter ``n/m ont validé``; the view carries None when ``expected < 3``."""

    validated: int
    expected: int


class MyAnswer(OutboundModel):
    """The recipient's own answer, with no timing field at all."""

    status: AnswerStatus
    text: str | None  # LOCKED or CAPTURED text
    draft_text: str | None  # draft restoration (NONE/DRAFT only)


class RevealTrack(OutboundModel):
    display_name: str
    folder: str
    title: str | None
    artist: str | None
    featuring: str | None = None
    album: str | None = None
    year: int | None = None


class RevealRow(OutboundModel):
    player_id: PlayerId
    text: str | None
    status: AnswerStatus
    elapsed_ms: int | None
    order: int | None
    near_tie: bool
    points: int


# --- round variants ----------------------------------------------------------------------


class RoundPending(OutboundModel):
    state: Literal["QUEUED", "PREPARING", "LOADING"]
    round_id: RoundId
    number: int
    wait_reason: Literal["pool_exhausted", "bridge_offline"] | None = None


class RoundCountdown(OutboundModel):
    state: Literal["COUNTDOWN"]
    round_id: RoundId
    number: int
    official_start_at: int


class RoundOpen(OutboundModel):
    """OPEN round as seen by a player and by a host in Player Mode (identical, patch 2)."""

    state: Literal["OPEN"]
    round_id: RoundId
    number: int
    official_start_at: int
    deadline: int
    my_answer: MyAnswer
    progress: Progress | None


class RoundPlayerReview(OutboundModel):
    auto_advance_at: int | None = None
    state: Literal["REVIEW"]
    round_id: RoundId
    number: int
    my_answer: MyAnswer


class RoundRevealed(OutboundModel):
    state: Literal["REVEALED"]
    round_id: RoundId
    number: int
    track: RevealTrack
    rows: list[RevealRow]  # LOCKED by order, then CAPTURED, then NONE


class McOpenRow(OutboundModel):
    player_id: PlayerId
    validated: bool  # MC-only live status and text; never in the player view
    text: str | None = None
    status: AnswerStatus = AnswerStatus.NONE


class RoundMcOpen(OutboundModel):
    state: Literal["OPEN"]
    round_id: RoundId
    number: int
    official_start_at: int
    deadline: int
    validated: int
    expected: int
    per_player: list[McOpenRow]


class ReviewRow(OutboundModel):
    judgement: str = "manual"
    title_correct: bool | None = None
    artist_correct: bool | None = None
    custom_correct: bool | None = None
    score_revision: int = 0
    player_id: PlayerId
    text: str | None
    status: AnswerStatus
    elapsed_ms: int | None
    order: int | None
    near_tie: bool
    late_start_ms: int | None  # None = no READY received
    points_draft: int
    reviewed: bool = False
    score_before: int = 0
    received_at_wall_ms: int | None = None


class ReviewRound(OutboundModel):
    full_review_allowed: bool = False
    bridge_online: bool = False
    round_id: RoundId
    number: int
    track: RevealTrack | None
    answers: list[ReviewRow]
    included: bool
    state: str
    close_reason: str | None
    recovery_interrupted: bool
    excerpt_duration_ms: int | None
    track_duration_ms: int | None
    metadata_revision: int = 0


class RoundHostReview(OutboundModel):
    auto_advance_at: int | None = None
    state: Literal["REVIEW"]
    round_id: RoundId
    number: int
    official_start_at: int
    answers: list[ReviewRow]  # LOCKED by order, then CAPTURED, then no answer
    ending: bool  # end_game{score} requested: publish then final review
    track: RevealTrack | None = None
    recovery_interrupted: bool = False


PlayerRound = Annotated[
    RoundPending | RoundCountdown | RoundOpen | RoundPlayerReview | RoundRevealed,
    Field(discriminator="state"),
]
HostPmRound = Annotated[
    RoundPending | RoundCountdown | RoundOpen | RoundPlayerReview | RoundRevealed,
    Field(discriminator="state"),
]
HostMcRound = Annotated[
    RoundPending | RoundCountdown | RoundMcOpen | RoundPlayerReview | RoundRevealed,
    Field(discriminator="state"),
]

# --- host and MC panels ------------------------------------------------------------------


class PlayerOps(OutboundModel):
    """Operational state of a player for hosts; NO answer field."""

    player_id: PlayerId
    connection: ConnectionState
    audio_state: AudioState
    audio_error: AudioErrorCode | None
    ready: bool
    late_ms: int | None
    rtt_min_ms: int | None
    offset_ms: int | None


class ReadyCheck(OutboundModel):
    ready: int
    expected: int
    timeout_at: int
    can_force: bool


class BridgeStatus(OutboundModel):
    state: BridgeState
    name: str | None
    track_count: int
    jobs_in_flight: int


class BridgeDetail(OutboundModel):
    bridge_id: str
    name: str
    version: str
    protocol: int
    state: BridgeState
    track_count: int
    jobs_in_flight: int
    formats: list[str]
    allow_full_review: bool
    source_error: str | None


class PoolStatus(OutboundModel):
    size: int
    remaining: int
    exhausted: bool
    fresh: int = 0
    played: int = 0
    unavailable: int = 0
    reserved: int = 0


class HistoryEntry(OutboundModel):
    judgement: str = "manual"
    title_correct: bool | None = None
    artist_correct: bool | None = None
    custom_correct: bool | None = None
    round_id: RoundId
    number: int
    text: str | None
    status: AnswerStatus
    elapsed_ms: int | None
    order: int | None
    near_tie: bool
    points: int
    track: RevealTrack | None = None
    received_at_wall_ms: int | None = None
    included: bool = True


class AdjustmentEntry(OutboundModel):
    kind: str = "adjustment"
    delta: int
    round_number: int | None
    note: str | None


class FinalReviewRow(OutboundModel):
    draft_note: str | None = None
    player_id: PlayerId
    score_before: int
    draft_delta: int
    score_after: int
    history: list[HistoryEntry]
    adjustments: list[AdjustmentEntry]


class ManualTrackChoice(OutboundModel):
    round_number: int
    bridge_id: str | None
    track_id: str | None
    filename: str | None
    bridge_name: str | None
    folder: str | None
    title: str | None
    artist: str | None
    locked: bool
    manual: bool
    error: str | None


class HostPanel(OutboundModel):
    settings: GameSettings
    limits: ServerLimits
    commands: list[str]  # HOST commands allowed now
    start_blockers: list[StartBlocker]
    bridge: BridgeStatus
    pool: PoolStatus | None
    players_ops: list[PlayerOps]
    ready_check: ReadyCheck | None
    undo_round_id: RoundId | None
    last_play_id: PlayId | None
    final_review: list[FinalReviewRow] | None
    warnings: list[HostWarning]
    history: list[GameRecord] = Field(default_factory=list)
    history_count: int = 0
    bridges: list[BridgeDetail] = Field(default_factory=list)
    review_rounds: list[ReviewRound] = Field(default_factory=list)
    joins_locked: bool = False


class McTrackInfo(OutboundModel):
    """Track information for an MC host; never ``relpath`` nor ``track_id`` (spec §13)."""

    bridge_name: str
    folder: str
    filename: str
    display_name: str | None
    asset_state: AssetState | None


class McPanel(OutboundModel):
    manual_choices: list[ManualTrackChoice] = Field(default_factory=list)
    selection_revision: int = 0
    current_track: McTrackInfo | None
    upcoming: list[McTrackInfo]


class FinalAdjustmentShown(OutboundModel):
    note: str | None = None
    player_id: PlayerId
    delta: int


class FinalResults(OutboundModel):
    standings: list[StandingRow]
    podium: list[StandingRow]  # rank <= 3 (may exceed 3 rows on ties)
    rounds_played: int
    final_adjustments: list[FinalAdjustmentShown]
    recap: list[FinalReviewRow] = Field(default_factory=list)
    finished_at: int | None = None


class GameRecord(OutboundModel):
    version: Literal[2] = 2
    game_id: GameId
    finished_at: int
    players: list[ViewPlayer]
    results: FinalResults
    teams: list[TeamStanding] = Field(default_factory=list)
    started_at: int | None = None
    settings: GameSettings | None = None
    sources: list[ArchiveSource] = Field(default_factory=list)


class ArchiveSource(OutboundModel):
    bridge_id: str
    name: str


class HistoryItem(OutboundModel):
    game_id: GameId
    finished_at: int
    rounds_played: int
    participants: int


class HistoryResponse(OutboundModel):
    version: Literal[2] = 2
    items: list[HistoryItem]
    retained_bytes: int
    max_games: int
    max_bytes: int
    retention_days: int
    durable: bool


# --- root views --------------------------------------------------------------------------


class _ViewBase(OutboundModel):
    session: SessionInfo
    me: Me
    phase: GamePhase
    players: list[ViewPlayer]
    standings: list[StandingRow]
    game: GameInfo | None
    audio: AudioSlots
    play: PlayInfo | None
    final_results: FinalResults | None
    rules: GameRules | None = None
    paused: PauseInfo | None = None
    team_standings: list[TeamStanding] = Field(default_factory=list)


class PlayerView(_ViewBase):
    kind: Literal["player"]
    round: PlayerRound | None


class HostPlayerModeView(_ViewBase):
    kind: Literal["host_player"]
    round: HostPmRound | None
    host: HostPanel


class HostMcView(_ViewBase):
    kind: Literal["host_mc"]
    round: HostMcRound | None
    host: HostPanel
    mc: McPanel


AnyView = Annotated[PlayerView | HostPlayerModeView | HostMcView, Field(discriminator="kind")]
