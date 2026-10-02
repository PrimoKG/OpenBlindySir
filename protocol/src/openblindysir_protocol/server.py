"""Server → player WebSocket messages (spec §8.2)."""

from typing import Annotated, Literal

from pydantic import Field

from openblindysir_protocol.base import AssetId, OutboundModel, PlayId, RoundId
from openblindysir_protocol.enums import AnswerAckStatus
from openblindysir_protocol.errors import AnswerRejectReason, ErrorCode
from openblindysir_protocol.views import AnyView


class StateMsg(OutboundModel):
    """Full view of one recipient.

    ``v`` is a per-connection counter, bumped only when this recipient's view changed; it
    is never a global version, which would reveal other players' activity (patch 2).
    """

    t: Literal["STATE"]
    v: int
    view: AnyView


class Pong(OutboundModel):
    t: Literal["PONG"]
    c: float  # echo of the client's PING
    s: float  # server monotonic ms, read before any await


class PlayMsg(OutboundModel):
    t: Literal["PLAY"]
    play_id: PlayId
    asset_id: AssetId
    start_at: int  # server ms
    clip_offset: Annotated[float, Field(ge=0, le=120)]  # seconds into the clip


class StopMsg(OutboundModel):
    t: Literal["STOP"]
    play_id: PlayId
    stop_at: int | None = None


class AnswerAck(OutboundModel):
    """Acknowledgement of ANSWER_SUBMIT, with NO timing data (spec §8.2)."""

    t: Literal["ANSWER_ACK"]
    round_id: RoundId
    status: AnswerAckStatus
    reason: AnswerRejectReason | None


class ErrorMsg(OutboundModel):
    t: Literal["ERROR"]
    code: ErrorCode


ServerMessage = Annotated[
    StateMsg | Pong | PlayMsg | StopMsg | AnswerAck | ErrorMsg, Field(discriminator="t")
]
