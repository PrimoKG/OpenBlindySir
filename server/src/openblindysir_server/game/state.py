"""In-memory session state (spec §13) and pure derived helpers.

No secret nor secret-derived value lives here: tokens and passwords stay in the shell.
"""

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from openblindysir_protocol.enums import (
    AnswerStatus,
    AssetFailureCode,
    AssetState,
    AudioErrorCode,
    AudioState,
    BridgeState,
    CancelReason,
    CloseReason,
    ConnectionState,
    EndGameMode,
    GamePhase,
    HostMode,
    JobStage,
    Role,
    RoundState,
)
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.config import CoreConfig
from openblindysir_server.game.effects import Play
from openblindysir_server.game.ids import IdFactory
from openblindysir_server.game.scoring import ScoreJournal

TERMINAL_ROUND_STATES = frozenset(
    {RoundState.REVIEW, RoundState.REVEALED, RoundState.FAILED, RoundState.CANCELLED}
)
LIVE_ROUND_STATES = frozenset(
    {
        RoundState.QUEUED,
        RoundState.PREPARING,
        RoundState.LOADING,
        RoundState.COUNTDOWN,
        RoundState.OPEN,
        RoundState.REVIEW,
    }
)
IN_FLIGHT_ASSET_STATES = frozenset(
    {AssetState.REQUESTED, AssetState.ENCODING, AssetState.UPLOADING}
)


@dataclass(frozen=True, slots=True, order=True)
class TrackRef:
    """Identity of a track: (bridge_id, track_id), ready for several Bridges (spec §11)."""

    bridge_id: str
    track_id: str


@dataclass(frozen=True, slots=True)
class CatalogEntryData:
    relpath: str  # server-side only (spec §13); never copied into a view
    folder: str
    ext: str
    size: int


@dataclass(slots=True)
class Catalog:
    bridge_id: str
    bridge_name: str
    catalog_hash: str
    entries: dict[str, CatalogEntryData]  # track_id -> entry
    scanned_folders: list[str] = field(default_factory=lambda: [""])
    source_error: str | None = None
    ambiguous_paths: tuple[str, ...] = ()
    scan_revision: int = 0


@dataclass(slots=True)
class BridgeInfo:
    bridge_id: str
    name: str
    version: str
    state: BridgeState
    catalog_hash: str
    track_count: int
    protocol: int = 6
    formats: tuple[str, ...] = ("aac",)
    allow_full_review: bool = False
    source_error: str | None = None


@dataclass(slots=True)
class PlaybackSample:
    play_id: str
    late_ms: float
    offset_ms: float
    rtt_min_ms: float
    out_latency_ms: float
    est_error_ms: float


@dataclass(slots=True)
class Player:
    id: str
    nickname: str
    nickname_key: str
    join_seq: int
    role: Role = Role.PLAYER
    host_mode: HostMode = HostMode.PLAYER
    connection: ConnectionState = ConnectionState.OFFLINE
    audio_state: AudioState = AudioState.LOCKED
    audio_asset_id: str | None = None
    audio_error: AudioErrorCode | None = None
    clock_offset_ms: float | None = None
    rtt_min_ms: float | None = None
    last_report: PlaybackSample | None = None
    client_version: str | None = None
    joined_at_mono: int = 0
    ever_connected: bool = False
    spectator: bool = False
    team: str | None = None


@dataclass(slots=True)
class Answer:
    player_id: str
    status: AnswerStatus = AnswerStatus.NONE
    text: str | None = None  # LOCKED or CAPTURED text
    draft_text: str = ""
    draft_last_changed_at: int | None = None  # diagnostics only, never ranks anything
    draft_last_changed_wall_ms: int | None = None
    received_at: int | None = None
    received_at_wall_ms: int | None = None
    elapsed_ms: int | None = None
    order: int | None = None
    near_tie: bool = False
    late_start_ms: int | None = None


@dataclass(slots=True)
class Listen:
    """Server-side measurement of when a player could hear the clip (late_start_ms)."""

    ready_at: int | None = None
    offline_since: int | None = None
    missed_ms: int = 0


@dataclass(slots=True)
class Slot:
    """A track slot: the current round's or a prefetch slot."""

    track_ref: TrackRef | None  # None: pool exhausted, waiting
    asset_id: str | None = None
    attempts: int = 0  # tracks tried for this slot
    same_track_retries: int = 0
    waiting_bridge: bool = False
    round_number: int = 0
    manual: bool = False
    manual_error: AssetFailureCode | None = None
    bridge_wait_since: int | None = None


@dataclass(frozen=True, slots=True)
class RevealInfo:
    """Track information shown at the reveal, built once at publish."""

    display_name: str
    folder: str
    title: str | None
    artist: str | None
    featuring: str | None = None
    album: str | None = None
    year: int | None = None
    aliases: dict[str, list[str]] | None = None
    cleared_fields: list[str] | None = None


@dataclass(frozen=True, slots=True)
class Metadata:
    cleared_fields: list[str] | None = None
    aliases: dict[str, list[str]] | None = None
    title: str | None = None
    artist: str | None = None
    featuring: str | None = None
    album: str | None = None
    year: int | None = None
    tags: list[str] | None = None
    linked_to: list[str] | None = None
    enabled: bool | None = None


@dataclass(frozen=True, slots=True)
class AutoMatch:
    criterion: str
    reference: str | None
    fragment: str | None
    similarity: float
    threshold: int
    status: str


@dataclass(slots=True)
class Round:
    id: str
    number: int
    slot: Slot
    state: RoundState
    created_at: int
    loading_since: int | None = None
    ready_deadline: int | None = None
    official_start_at: int | None = None  # written once, at the first PLAY
    plays: list[Play] = field(default_factory=list)
    stopped_play_ids: set[str] = field(default_factory=set)
    ended_play_ids: set[str] = field(default_factory=set)
    deadline: int | None = None
    closed_at: int | None = None
    close_reason: CloseReason | None = None
    cancel_reason: CancelReason | None = None
    answers: dict[str, Answer] = field(default_factory=dict)
    listen: dict[str, Listen] = field(default_factory=dict)
    decode_errors: set[str] = field(default_factory=set)
    playback_late_ms: list[float] = field(default_factory=list)
    score_draft: dict[str, int] = field(default_factory=dict)
    published_at: int | None = None
    published_event_ids: tuple[int, ...] = ()
    reveal: RevealInfo | None = None  # None unless state == REVEALED
    score_reviewed: set[str] = field(default_factory=set)
    paused_at: int | None = None
    pause_offset_s: float | None = None
    paused_total_ms: int = 0
    resume_at: int | None = None
    recovery_interrupted: bool = False
    pause_ready: bool = False
    previously_played: bool = False
    participant_ids: set[str] = field(default_factory=set)
    included: bool = True
    track_entry: CatalogEntryData | None = None
    bridge_name: str = ""
    metadata_revision: int = 0
    auto_advance_at: int | None = None
    judgements: dict[str, dict[str, bool | None]] = field(default_factory=dict)
    score_revisions: dict[str, int] = field(default_factory=dict)
    auto_config: "Settings | None" = None
    auto_reference: Metadata | None = None
    auto_evidence: dict[str, list[AutoMatch]] = field(default_factory=dict)
    auto_overrides: set[str] = field(default_factory=set)
    matcher_version: int = 1
    finale_awarded: set[str] | None = None
    finale_wave_at: int | None = None


@dataclass(slots=True)
class UploadInfo:
    size: int
    sha256: str
    mime: str


@dataclass(slots=True)
class AssetRecord:
    asset_id: str
    track_ref: TrackRef
    job_id: str
    state: AssetState
    requested_at: int
    job_deadline: int
    stage: JobStage | None = None
    upload: UploadInfo | None = None
    actual_start_s: float | None = None
    clip_duration_ms: int | None = None
    track_duration_ms: int | None = None
    title: str | None = None
    artist: str | None = None
    error: AssetFailureCode | None = None
    input_duration_s: float | None = None
    source_revision: str | None = None
    normalize_audio: bool = True


@dataclass(slots=True)
class Settings:
    scoring_mode: str = "manual"
    acceptance_threshold: int = 90
    answer_fields: list[str] = field(default_factory=lambda: ["title", "artist"])
    album_points: int = 1
    year_points: int = 1
    featuring_points: int = 1
    auto_advance: bool = True
    intermission_s: int = 2
    custom_points: int = 1
    rounds: int = 20
    clip_seconds: int = 25
    answer_grace_s: int = 15
    sources: list[tuple[str, str]] = field(default_factory=list)  # (bridge_id, folder_prefix)
    auto_start: bool = True
    prefetch_depth: int = 1
    allow_repeats: bool = False
    answer_mode: str = "both"
    title_points: int = 1
    artist_points: int = 1
    instructions: str = ""
    captured_policy: str = "manual"
    normalize_audio: bool = True
    avoid_silence: bool = True
    balance_folders: bool = False

    def copy(self) -> "Settings":
        return Settings(
            scoring_mode=self.scoring_mode,
            acceptance_threshold=self.acceptance_threshold,
            answer_fields=list(self.answer_fields),
            album_points=self.album_points,
            year_points=self.year_points,
            featuring_points=self.featuring_points,
            auto_advance=self.auto_advance,
            intermission_s=self.intermission_s,
            custom_points=self.custom_points,
            rounds=self.rounds,
            clip_seconds=self.clip_seconds,
            answer_grace_s=self.answer_grace_s,
            sources=list(self.sources),
            auto_start=self.auto_start,
            prefetch_depth=self.prefetch_depth,
            allow_repeats=self.allow_repeats,
            answer_mode=self.answer_mode,
            title_points=self.title_points,
            artist_points=self.artist_points,
            instructions=self.instructions,
            captured_policy=self.captured_policy,
            normalize_audio=self.normalize_audio,
            avoid_silence=self.avoid_silence,
            balance_folders=self.balance_folders,
        )


@dataclass(slots=True)
class GameState:
    game_id: str
    manual_tracks: dict[int, TrackRef] = field(default_factory=dict)
    selection_revision: int = 0
    phase: GamePhase = GamePhase.LOBBY
    settings: Settings = field(default_factory=Settings)
    queue: deque[TrackRef] = field(default_factory=deque)
    pipeline: deque[Slot] = field(default_factory=deque)  # prefetch slots N+1 (N+2)
    rounds: list[Round] = field(default_factory=list)  # append-only history
    current_index: int | None = None
    unavailable: set[TrackRef] = field(default_factory=set)
    ending: EndGameMode | None = None
    final_draft: dict[str, int] = field(default_factory=dict)
    final_notes: dict[str, str] = field(default_factory=dict)
    finale_round_id: str | None = None
    finale_revealed: list[str] = field(default_factory=list)
    podium_skipped: bool = False
    finale_play: Play | None = None
    finale_audio_revision: int = 0
    finalized_at: int | None = None
    finalized_wall_ms: int | None = None
    started_wall_ms: int | None = None
    applied_op_ids: set[str] = field(default_factory=set)
    cache_full_round: str | None = None


@dataclass(slots=True)
class SessionState:
    epoch: str
    started_at: Instant
    config: CoreConfig
    players: dict[str, Player]  # insertion order = arrival order
    game: GameState
    journal: ScoreJournal
    played: set[TrackRef]  # session scope (spec §6.9)
    catalogs: dict[str, Catalog]
    bridges: dict[str, BridgeInfo]
    assets: dict[str, AssetRecord]
    jobs: dict[str, str]  # job_id -> asset_id
    asset_ready: dict[str, dict[str, int]]  # asset_id -> player_id -> ready_received_at
    ids: IdFactory
    rng: random.Random
    version: int = 0
    last_at: int = 0
    join_seq: int = 0
    touched: bool = False
    recovered: bool = False
    archives: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[TrackRef, Metadata] = field(default_factory=dict)
    metadata_revision: int = 0
    imported_metadata: dict[TrackRef, Metadata] = field(default_factory=dict)
    metadata_issues: list[dict[str, Any]] = field(default_factory=list)
    consumed_cancelled: set[TrackRef] = field(default_factory=set)
    joins_locked: bool = False
    persistence_status: str = "disabled"


# --- derived helpers ---------------------------------------------------------------------


def current_round(g: GameState) -> Round | None:
    """The current round (IN_GAME only), designated explicitly by ``current_index``."""
    if g.phase is not GamePhase.IN_GAME or g.current_index is None:
        return None
    return g.rounds[g.current_index]


def undo_target(g: GameState) -> Round | None:
    """The round ``undo_publish`` may revert (spec §6.5), or None.

    The most recent REVEALED round, provided no later round ever reached COUNTDOWN, whatever
    its state (FAILED, CANCELLED, or the live QUEUED/PREPARING/LOADING round).
    """
    if g.phase is not GamePhase.IN_GAME:
        return None
    for index in range(len(g.rounds) - 1, -1, -1):
        if g.rounds[index].state is RoundState.REVEALED:
            later = g.rounds[index + 1 :]
            if all(r.official_start_at is None for r in later):
                return g.rounds[index]
            return None
    return None


def is_participant(p: Player) -> bool:
    """Answers rounds: not removed and not an MC host."""
    if p.connection is ConnectionState.REMOVED or p.spectator:
        return False
    return p.role is Role.PLAYER or p.host_mode is HostMode.PLAYER


def active_players(s: SessionState) -> list[Player]:
    return [p for p in s.players.values() if p.connection is not ConnectionState.REMOVED]


def online_participants(s: SessionState) -> list[Player]:
    return [
        p
        for p in s.players.values()
        if is_participant(p) and p.connection is ConnectionState.ONLINE
    ]


def active_play(r: Round) -> Play | None:
    """The last play of the round if neither stopped nor ended."""
    if not r.plays:
        return None
    play = r.plays[-1]
    if play.play_id in r.stopped_play_ids or play.play_id in r.ended_play_ids:
        return None
    return play


def revealed_count(g: GameState) -> int:
    return sum(
        1 for r in g.rounds if r.included and r.state in {RoundState.REVIEW, RoundState.REVEALED}
    )


def clip_ms(s: SessionState, r: Round) -> int:
    """Duration of the round's clip, from the stored asset (falls back to the setting)."""
    asset = s.assets.get(r.slot.asset_id) if r.slot.asset_id else None
    if asset is not None and asset.clip_duration_ms is not None:
        return asset.clip_duration_ms
    return s.game.settings.clip_seconds * 1000


def late_start_ms(r: Round, player_id: str) -> int | None:
    """``max(0, ready_at − S) + missed_ms`` for closed outages; None without READY."""
    listen = r.listen.get(player_id)
    if listen is None or listen.ready_at is None or r.official_start_at is None:
        return None
    return max(0, listen.ready_at - r.official_start_at) + listen.missed_ms
