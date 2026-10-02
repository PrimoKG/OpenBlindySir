"""Per-recipient views sent in ``STATE`` (spec §6.8, §8.2).

There is one root model per audience (``PlayerView``, ``HostPlayerModeView``,
``HostMcView``) and audience-specific round unions, so a datum that an audience must not
see has no field to live in. Names such as ``relpath``, ``track_id`` or
``draft_last_changed_at`` exist in no view model.
"""

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
    validated: bool  # per-player status without text


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
    player_id: PlayerId
    text: str | None
    status: AnswerStatus
    elapsed_ms: int | None
    order: int | None
    near_tie: bool
    late_start_ms: int | None  # None = no READY received
    points_draft: int


class RoundHostReview(OutboundModel):
    state: Literal["REVIEW"]
    round_id: RoundId
    number: int
    official_start_at: int
    answers: list[ReviewRow]  # LOCKED by order, then CAPTURED, then no answer
    ending: bool  # end_game{score} requested: publish then final review


PlayerRound = Annotated[
    RoundPending | RoundCountdown | RoundOpen | RoundPlayerReview | RoundRevealed,
    Field(discriminator="state"),
]
HostPmRound = Annotated[
    RoundPending | RoundCountdown | RoundOpen | RoundHostReview | RoundRevealed,
    Field(discriminator="state"),
]
HostMcRound = Annotated[
    RoundPending | RoundCountdown | RoundMcOpen | RoundHostReview | RoundRevealed,
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


class PoolStatus(OutboundModel):
    size: int
    remaining: int
    exhausted: bool


class HistoryEntry(OutboundModel):
    round_id: RoundId
    number: int
    text: str | None
    status: AnswerStatus
    elapsed_ms: int | None
    order: int | None
    near_tie: bool
    points: int


class AdjustmentEntry(OutboundModel):
    delta: int
    round_number: int | None
    note: str | None


class FinalReviewRow(OutboundModel):
    player_id: PlayerId
    score_before: int
    draft_delta: int
    score_after: int
    history: list[HistoryEntry]
    adjustments: list[AdjustmentEntry]


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


class McTrackInfo(OutboundModel):
    """Track information for an MC host; never ``relpath`` nor ``track_id`` (spec §13)."""

    bridge_name: str
    folder: str
    filename: str
    display_name: str | None
    asset_state: AssetState | None


class McPanel(OutboundModel):
    current_track: McTrackInfo | None
    upcoming: list[McTrackInfo]


class FinalAdjustmentShown(OutboundModel):
    player_id: PlayerId
    delta: int


class FinalResults(OutboundModel):
    standings: list[StandingRow]
    podium: list[StandingRow]  # rank <= 3 (may exceed 3 rows on ties)
    rounds_played: int
    final_adjustments: list[FinalAdjustmentShown]


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
