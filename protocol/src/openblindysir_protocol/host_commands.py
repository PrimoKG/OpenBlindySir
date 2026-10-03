"""HOST commands (spec §8.2): envelope ``{t:"HOST", cmd, round_id | expected_phase, args}``.

Every variant declares exactly one idempotency key in the envelope (``round_id`` or
``expected_phase``) as a required field; the other one is refused by ``extra="forbid"``.
"""

from collections.abc import Mapping
from typing import Annotated, Any, Final, Literal, get_args

from pydantic import Field, StringConstraints, model_validator

from openblindysir_protocol.base import (
    BridgeId,
    InboundModel,
    NonZeroPoints,
    NoteText,
    OpId,
    PlayerId,
    PlayId,
    Points,
    RoundId,
    ServerMs,
    TrackId,
)
from openblindysir_protocol.enums import EndGameMode, GamePhase, HostMode
from openblindysir_protocol.metadata import MusicalMetadata
from openblindysir_protocol.settings import SettingsPatch

AnyPhase = Literal[
    GamePhase.LOBBY, GamePhase.IN_GAME, GamePhase.FINAL_SCORE_REVIEW, GamePhase.FINAL_RESULTS
]


class SelectTrackArgs(InboundModel):
    round_number: Annotated[int, Field(ge=1, le=100)]
    expected_revision: Annotated[int, Field(ge=0)]
    bridge_id: BridgeId | None = None
    track_id: TrackId | None = None

    @model_validator(mode="after")
    def paired_reference(self) -> "SelectTrackArgs":
        if (self.bridge_id is None) != (self.track_id is None):
            raise ValueError("bridge_id and track_id must be paired")
        return self


class HostSelectTrack(InboundModel):
    t: Literal["HOST"]
    cmd: Literal["select_track"]
    expected_phase: Literal[GamePhase.LOBBY, GamePhase.IN_GAME]
    args: SelectTrackArgs


class EmptyArgs(InboundModel):
    pass


class SetModeArgs(InboundModel):
    mode: HostMode


class EndGameArgs(InboundModel):
    current_round: EndGameMode


class PlayIdArgs(InboundModel):
    play_id: PlayId


class AddTimeArgs(InboundModel):
    expected_deadline: ServerMs


class ScoreDraftArgs(InboundModel):
    player_id: PlayerId
    points: Points


class AdjustArgs(InboundModel):
    player_id: PlayerId
    delta: NonZeroPoints
    round_id: RoundId | None = None
    note: NoteText | None = None
    op_id: OpId


class FinalSetArgs(InboundModel):
    player_id: PlayerId
    delta: Points


class PlayerArgs(InboundModel):
    player_id: PlayerId


class RenameArgs(InboundModel):
    player_id: PlayerId
    nickname: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class ParticipationArgs(InboundModel):
    player_id: PlayerId
    spectator: bool = False
    team: Annotated[str, StringConstraints(max_length=40)] | None = None


class PublishArgs(InboundModel):
    confirm_unreviewed: bool = False


class TrackMetadataArgs(MusicalMetadata):
    pass


class JoinLockArgs(InboundModel):
    locked: bool


class _Host(InboundModel):
    t: Literal["HOST"]


class HostConfigure(_Host):
    cmd: Literal["configure"]
    expected_phase: Literal[GamePhase.LOBBY, GamePhase.IN_GAME, GamePhase.FINAL_RESULTS]
    args: SettingsPatch
    start_game: bool = False


class HostSetMode(_Host):
    cmd: Literal["set_mode"]
    expected_phase: AnyPhase
    args: SetModeArgs


class HostStartGame(_Host):
    cmd: Literal["start_game"]
    expected_phase: Literal[GamePhase.LOBBY]
    args: EmptyArgs


class HostNewGame(_Host):
    cmd: Literal["new_game"]
    expected_phase: Literal[GamePhase.FINAL_RESULTS]
    args: EmptyArgs


class HostEndGame(_Host):
    cmd: Literal["end_game"]
    round_id: RoundId | None = None
    expected_phase: AnyPhase | None = None
    args: EndGameArgs

    @model_validator(mode="after")
    def _key(self) -> "HostEndGame":
        if (self.round_id is None) == (self.expected_phase is None):
            raise ValueError("exactly one idempotency key required")
        return self


class HostEndSession(_Host):
    cmd: Literal["end_session"]
    expected_phase: AnyPhase
    args: EmptyArgs


class HostNext(_Host):
    cmd: Literal["next"]
    round_id: RoundId
    args: EmptyArgs


class HostForceStart(_Host):
    cmd: Literal["force_start"]
    round_id: RoundId
    args: EmptyArgs


class HostReplay(_Host):
    cmd: Literal["replay"]
    round_id: RoundId
    args: PlayIdArgs


class HostStop(_Host):
    cmd: Literal["stop"]
    round_id: RoundId
    args: PlayIdArgs


class HostPause(_Host):
    cmd: Literal["pause"]
    round_id: RoundId
    args: EmptyArgs


class HostResume(_Host):
    cmd: Literal["resume"]
    round_id: RoundId
    args: EmptyArgs


class HostSkip(_Host):
    cmd: Literal["skip"]
    round_id: RoundId
    args: EmptyArgs


class HostAddTime(_Host):
    cmd: Literal["add_time"]
    round_id: RoundId
    args: AddTimeArgs


class HostClose(_Host):
    cmd: Literal["close"]
    round_id: RoundId
    args: EmptyArgs


class HostScoreDraft(_Host):
    cmd: Literal["score_draft"]
    round_id: RoundId
    args: ScoreDraftArgs


class HostPublish(_Host):
    cmd: Literal["publish"]
    round_id: RoundId
    args: PublishArgs


class HostTrackMetadata(_Host):
    cmd: Literal["track_metadata"]
    round_id: RoundId
    args: TrackMetadataArgs


class HostUndoPublish(_Host):
    """``round_id`` is the most recent REVEALED round (``host.undo_round_id``), not the
    current round once ``next`` was clicked (spec §6.5 window)."""

    cmd: Literal["undo_publish"]
    round_id: RoundId
    args: EmptyArgs


class HostAdjust(_Host):
    cmd: Literal["adjust"]
    expected_phase: Literal[GamePhase.IN_GAME]
    args: AdjustArgs


class HostToFinalReview(_Host):
    cmd: Literal["to_final_review"]
    round_id: RoundId
    args: EmptyArgs


class HostFinalSet(_Host):
    """Sets the draft VALUE of a final adjustment (not an increment; 0 clears)."""

    cmd: Literal["final_set"]
    expected_phase: Literal[GamePhase.FINAL_SCORE_REVIEW]
    args: FinalSetArgs


class HostFinalReset(_Host):
    cmd: Literal["final_reset"]
    expected_phase: Literal[GamePhase.FINAL_SCORE_REVIEW]
    args: EmptyArgs


class HostFinalValidate(_Host):
    cmd: Literal["final_validate"]
    expected_phase: Literal[GamePhase.FINAL_SCORE_REVIEW]
    args: PublishArgs


class HostJoinLock(_Host):
    cmd: Literal["join_lock"]
    expected_phase: AnyPhase
    args: JoinLockArgs


class HostKick(_Host):
    cmd: Literal["kick"]
    expected_phase: AnyPhase
    args: PlayerArgs


class HostRename(_Host):
    cmd: Literal["rename"]
    expected_phase: AnyPhase
    args: RenameArgs


class HostParticipation(_Host):
    cmd: Literal["participation"]
    expected_phase: Literal[GamePhase.LOBBY]
    args: ParticipationArgs


HostCommandVariant = (
    HostSelectTrack
    | HostConfigure
    | HostSetMode
    | HostStartGame
    | HostNewGame
    | HostEndGame
    | HostEndSession
    | HostNext
    | HostForceStart
    | HostReplay
    | HostStop
    | HostPause
    | HostResume
    | HostSkip
    | HostAddTime
    | HostClose
    | HostScoreDraft
    | HostPublish
    | HostTrackMetadata
    | HostUndoPublish
    | HostAdjust
    | HostToFinalReview
    | HostFinalSet
    | HostFinalReset
    | HostFinalValidate
    | HostKick
    | HostRename
    | HostParticipation
    | HostJoinLock
)
HostCommand = Annotated[HostCommandVariant, Field(discriminator="cmd")]

HOST_COMMAND_NAMES: Final[tuple[str, ...]] = tuple(
    get_args(variant.model_fields["cmd"].annotation)[0] for variant in get_args(HostCommandVariant)
)

_ROUND = "r_round01"
_PLAYER = "p_player01"
_PLAY = "pl_play01"

# One valid JSON example per command, used by the permission test (spec §20.1 item 6).
HOST_COMMAND_EXAMPLES: Final[Mapping[str, dict[str, Any]]] = {
    "select_track": {
        "expected_phase": "LOBBY",
        "args": {"round_number": 1, "expected_revision": 0},
    },
    "configure": {"expected_phase": "LOBBY", "args": {"rounds": 10}},
    "set_mode": {"expected_phase": "LOBBY", "args": {"mode": "mc"}},
    "start_game": {"expected_phase": "LOBBY", "args": {}},
    "new_game": {"expected_phase": "FINAL_RESULTS", "args": {}},
    "end_game": {"round_id": _ROUND, "args": {"current_round": "score"}},
    "end_session": {"expected_phase": "LOBBY", "args": {}},
    "next": {"round_id": _ROUND, "args": {}},
    "force_start": {"round_id": _ROUND, "args": {}},
    "replay": {"round_id": _ROUND, "args": {"play_id": _PLAY}},
    "stop": {"round_id": _ROUND, "args": {"play_id": _PLAY}},
    "pause": {"round_id": _ROUND, "args": {}},
    "resume": {"round_id": _ROUND, "args": {}},
    "skip": {"round_id": _ROUND, "args": {}},
    "add_time": {"round_id": _ROUND, "args": {"expected_deadline": 1000}},
    "close": {"round_id": _ROUND, "args": {}},
    "score_draft": {"round_id": _ROUND, "args": {"player_id": _PLAYER, "points": 2}},
    "publish": {"round_id": _ROUND, "args": {}},
    "track_metadata": {"round_id": _ROUND, "args": {"title": "Example", "artist": "Example"}},
    "undo_publish": {"round_id": _ROUND, "args": {}},
    "adjust": {
        "expected_phase": "IN_GAME",
        "args": {"player_id": _PLAYER, "delta": -1, "op_id": "op-000001"},
    },
    "to_final_review": {"round_id": _ROUND, "args": {}},
    "final_set": {
        "expected_phase": "FINAL_SCORE_REVIEW",
        "args": {"player_id": _PLAYER, "delta": 2},
    },
    "final_reset": {"expected_phase": "FINAL_SCORE_REVIEW", "args": {}},
    "final_validate": {"expected_phase": "FINAL_SCORE_REVIEW", "args": {}},
    "kick": {"expected_phase": "LOBBY", "args": {"player_id": _PLAYER}},
    "rename": {"expected_phase": "LOBBY", "args": {"player_id": _PLAYER, "nickname": "Yo"}},
    "participation": {"expected_phase": "LOBBY", "args": {"player_id": _PLAYER}},
    "join_lock": {"expected_phase": "LOBBY", "args": {"locked": True}},
}
