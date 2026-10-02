"""Player → server WebSocket messages (spec §8.2)."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from openblindysir_protocol.base import AnswerText, AssetId, InboundModel, PlayId, RoundId
from openblindysir_protocol.enums import AudioErrorCode, AudioState
from openblindysir_protocol.host_commands import HostCommand


class Hello(InboundModel):
    t: Literal["HELLO"]
    client_version: Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z.+-]{1,32}$")]
    protocol: Annotated[int, Field(ge=0, le=10_000)]


class Ping(InboundModel):
    t: Literal["PING"]
    c: Annotated[float, Field(ge=0, le=1e13)]  # client performance.now(), echoed in PONG


class ClockInfo(InboundModel):
    offset: Annotated[float, Field(ge=-1e13, le=1e13)] | None  # θ in ms; None before a burst
    rtt_min: Annotated[float, Field(ge=0, le=60_000)] | None


class AudioStatus(InboundModel):
    t: Literal["AUDIO_STATUS"]
    state: AudioState
    asset_id: AssetId | None = None
    error: AudioErrorCode | None = None
    clock: ClockInfo

    @model_validator(mode="after")
    def _consistent(self) -> "AudioStatus":
        if self.state in {AudioState.LOADING, AudioState.READY, AudioState.PLAYING}:
            if self.asset_id is None or self.error is not None:
                raise ValueError("LOADING/READY/PLAYING require asset_id and no error")
        elif self.state is AudioState.ERROR:
            if self.error is None:
                raise ValueError("ERROR requires an error code")
        elif self.asset_id is not None or self.error is not None:
            raise ValueError("LOCKED/IDLE take neither asset_id nor error")
        return self


class PlaybackReport(InboundModel):
    """Synchronisation measurement: informative only, never used for timing or scoring."""

    t: Literal["PLAYBACK_REPORT"]
    play_id: PlayId
    late_ms: Annotated[float, Field(ge=-600_000, le=600_000)]
    offset: Annotated[float, Field(ge=-1e13, le=1e13)]
    rtt_min: Annotated[float, Field(ge=0, le=60_000)]
    out_latency: Annotated[float, Field(ge=0, le=5_000)]
    est_error_ms: Annotated[float, Field(ge=0, le=60_000)]


class AnswerDraft(InboundModel):
    t: Literal["ANSWER_DRAFT"]
    round_id: RoundId
    text: AnswerText  # empty allowed (clearing)


class AnswerSubmit(InboundModel):
    """Definitive validation, timestamped by the server only (spec §6.3).

    No other field is accepted: a client timestamp is a schema error (extra="forbid").
    An empty text is not a schema error: the core answers ANSWER_ACK rejected/empty.
    """

    t: Literal["ANSWER_SUBMIT"]
    round_id: RoundId
    text: AnswerText


ClientMessage = Annotated[
    Hello | Ping | AudioStatus | PlaybackReport | AnswerDraft | AnswerSubmit | HostCommand,
    Field(discriminator="t"),
]
