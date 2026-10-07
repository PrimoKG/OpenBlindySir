"""Effects returned by the core for the shell to execute after the mutation (IO after)."""

from dataclasses import dataclass
from typing import Literal

from openblindysir_protocol.enums import AnswerAckStatus
from openblindysir_protocol.errors import AnswerRejectReason, CloseCode, ErrorCode

LogValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class Play:
    play_id: str
    asset_id: str
    start_at: int
    clip_offset_s: float
    ends_at: int  # start_at + remaining clip duration


@dataclass(frozen=True, slots=True)
class SendPlay:
    """Broadcast PLAY to every open player connection, before the next STATE."""

    play: Play


@dataclass(frozen=True, slots=True)
class SendStop:
    play_id: str
    stop_at: int | None = None


@dataclass(frozen=True, slots=True)
class SendAck:
    player_id: str
    round_id: str
    status: AnswerAckStatus
    reason: AnswerRejectReason | None


@dataclass(frozen=True, slots=True)
class SendError:
    player_id: str
    code: ErrorCode


@dataclass(frozen=True, slots=True)
class RequestPrepare:
    bridge_id: str
    job_id: str
    asset_id: str
    track_id: str
    start_fraction: float
    duration_s: float
    normalize_audio: bool = True
    avoid_silence: bool = True
    exact_start: float | None = None
    review_mode: Literal["excerpt", "full", "preview"] | None = None
    replay_sha256: str | None = None
    expected_source_revision: str | None = None


@dataclass(frozen=True, slots=True)
class CancelJob:
    bridge_id: str
    job_id: str


@dataclass(frozen=True, slots=True)
class CloseConnection:
    player_id: str
    code: CloseCode | None  # None = normal closure (1000)


@dataclass(frozen=True, slots=True)
class RevokeTokens:
    player_ids: tuple[str, ...] | Literal["ALL"]


@dataclass(frozen=True, slots=True)
class ResetSession:
    """end_session: the shell clears its authentication, cache and connections."""


@dataclass(frozen=True, slots=True)
class Log:
    """A log event. Never carries answer text, a path, a track name or a secret (spec §21)."""

    event: str
    fields: tuple[tuple[str, LogValue], ...] = ()


Effect = (
    SendPlay
    | SendStop
    | SendAck
    | SendError
    | RequestPrepare
    | CancelJob
    | CloseConnection
    | RevokeTokens
    | ResetSession
    | Log
)


class EffectSink:
    """Collects the effects of one dispatch, in order."""

    def __init__(self) -> None:
        self._effects: list[Effect] = []

    def add(self, effect: Effect) -> None:
        self._effects.append(effect)

    def log(self, event: str, **fields: LogValue) -> None:
        self._effects.append(Log(event, tuple(fields.items())))

    def freeze(self) -> tuple[Effect, ...]:
        return tuple(self._effects)


@dataclass(frozen=True, slots=True)
class Outcome:
    effects: tuple[Effect, ...]
    error: ErrorCode | None
    value: object | None
    version: int
    changed: bool  # the state version was incremented by this dispatch
